import os
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import db_utils
from logger import log

MAX_WORKERS = 10
cache = {}

load_dotenv()

from requests.adapters import HTTPAdapter

class MuleSoftAuthError(Exception):
    """Raised when Anypoint credentials are expired or invalid."""
    pass

class MuleSoftManager:
    def __init__(self):
        # Enable connection pooling to dramatically reduce TLS handshake / TCP overhead
        self.http_session = requests.Session()
        adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.http_session.mount('https://', adapter)
        self.http_session.mount('http://', adapter)
        
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.refresh_configs()

    def refresh_configs(self):
        """Reset all session/auth tokens to force fresh fetch from DB settings."""
        self.session_cookie = None
        self.xsrf_token = None
        self.access_token = None
        self.using_bearer_override = False
        # Clear local cache to ensure fresh data
        cache.clear()

    def check_connection(self):
        """Validates if we have a working connection to Anypoint."""
        try:
            # Ensure we have some form of auth
            if not self.access_token and not self.session_cookie:
                if not self.authenticate_from_db():
                    return False
            
            # Call /me to verify token validity
            url = f"{self.anypoint_url}/accounts/api/me"
            res = self.http_session.get(url, headers=self.get_headers(), timeout=5)
            return res.status_code == 200
        except:
            return False

    def authenticate_from_db(self):
        bearer = db_utils.get_setting('mule_bearer')
        if bearer:
            self.access_token = bearer.replace('Bearer ', '').strip()
            self.using_bearer_override = True
            return True

        self.using_bearer_override = False
        client_id = db_utils.get_setting('mule_client_id')
        client_secret = db_utils.get_setting('mule_client_secret')
        if client_id and client_secret:
            try:
                log.info(f"Attempting OAuth2 login for Client ID: {client_id[:8]}...")
                res = self.http_session.post(
                    f"{self.anypoint_url}/accounts/api/v2/oauth2/token", 
                    json={
                        "client_id": client_id, 
                        "client_secret": client_secret, 
                        "grant_type": "client_credentials"
                    },
                    timeout=10
                )
                if res.status_code == 200:
                    self.access_token = res.json().get('access_token')
                    log.info("OAuth2 Authentication Successful")
                    return True
                else:
                    log.error(f"OAuth2 Failed: {res.status_code} - {res.text}")
            except Exception as e:
                log.error(f"MuleSoft Auth Error: {e}")
        return False

    def set_session(self, curl_string):
        """Extracts the HTTPOnly Cookie header and X-XSRF-TOKEN from a raw cURL string."""
        import re
        cookie_match = re.search(r"-H\s+['\"](?:cookie|Cookie)\s*:\s*(.+?)['\"]", curl_string)
        if cookie_match:
            self.session_cookie = cookie_match.group(1)
        # Alternate fallback if it's passed as -b
        b_match = re.search(r"-b\s+['\"](.+?)['\"]", curl_string)
        if b_match and not self.session_cookie:
            self.session_cookie = b_match.group(1)

        xsrf_match = re.search(r"-H\s+['\"]x-xsrf-token\s*:\s*(.+?)['\"]", curl_string, re.IGNORECASE)
        if xsrf_match:
            self.xsrf_token = xsrf_match.group(1)
        elif self.session_cookie:
            # Fallback extract from cookie if header doesn't exist explicitly
            token_match = re.search(r'(?:XSRF-TOKEN|_csrf)=([^;]+)', self.session_cookie, re.IGNORECASE)
            if token_match:
                self.xsrf_token = token_match.group(1)
        
        if self.session_cookie and self.xsrf_token:
            log.info("Successfully parsed Secure Cookie and XSRF-TOKEN from cURL")
            return True
        else:
            log.warning("Failed to extract either Cookie or XSRF Token from cURL.")
            return False

    def get_headers(self):
        if not self.access_token and not self.session_cookie:
            self.authenticate_from_db()
            
        headers = {
            "Accept": "application/json, text/plain, */*"
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self.session_cookie:
            headers["Cookie"] = self.session_cookie
            if self.xsrf_token:
                headers["X-XSRF-TOKEN"] = self.xsrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"
        return headers

    def get_organizations(self):
        """Fetches the user profile which contains the list of organizations."""
        url_me = f"{self.anypoint_url}/accounts/api/me"
        url_orgs = f"{self.anypoint_url}/accounts/api/organizations"
        try:
            res = self.http_session.get(url_me, headers=self.get_headers())
            
            if res.status_code == 401:
                if self.using_bearer_override:
                    log.error("Manual Bearer Token Expired. Skipping fallback.")
                    raise MuleSoftAuthError("Bearer Token Expired")
                
                log.warning("OAuth Token expired. Re-auth...")
                self.access_token = None
                res = self.http_session.get(url_me, headers=self.get_headers())

            log.debug(f"MuleSoft Org Fetch Status (me): {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                if 'user' in data:
                    return data.get('user', {}).get('memberOfOrganizations', [])
                elif 'memberOfOrganizations' in data:
                    return data.get('memberOfOrganizations', [])
            elif res.status_code == 401:
                raise MuleSoftAuthError("Unauthorized")
            else:
                log.warning(f"'/me' failed with {res.status_code}. Attempting Connected App fallback to '/organizations'...")
                res_orgs = self.http_session.get(url_orgs, headers=self.get_headers())
                log.debug(f"MuleSoft Org Fetch Status (orgs): {res_orgs.status_code}")
                if res_orgs.status_code == 200:
                    data_orgs = res_orgs.json()
                    if isinstance(data_orgs, list): return data_orgs
                    if 'data' in data_orgs: return data_orgs.get('data', [])
                    return [data_orgs]
                elif res_orgs.status_code == 401:
                    raise MuleSoftAuthError("Unauthorized")
                else:
                    log.error(f"Fallback Fetch Response: {res_orgs.text[:500]}")
            return []
        except MuleSoftAuthError:
            raise
        except Exception as e:
            log.error(f"MuleSoft Org Fetch Error: {e}")
            return []

    def get_environments(self, org_id):
        """Fetches environments for the specific organization."""
        url = f"{self.anypoint_url}/accounts/api/organizations/{org_id}/environments"
        try:
            res = self.http_session.get(url, headers=self.get_headers())
            
            if res.status_code == 401:
                if self.using_bearer_override:
                    raise MuleSoftAuthError("Bearer Token Expired")
                self.access_token = None
                res = self.http_session.get(url, headers=self.get_headers())

            if res.status_code == 200:
                return res.json().get('data', [])
            elif res.status_code == 401:
                raise MuleSoftAuthError("Unauthorized")
        except MuleSoftAuthError:
            raise
        except Exception as e:
            log.error(f"MuleSoft Env Fetch Error: {e}")
        return []

    def get_runtime_apps(self, org_id, env_id, extract_details=False):
        """Unified Discovery & Parallel Extraction with Bounded Concurrency"""
        headers = self.get_headers()
        headers.update({ "X-ANYPNT-ORG-ID": org_id, "X-ANYPNT-ENV-ID": env_id })
        
        # Check cache
        key = (org_id, env_id)
        if key in cache:
            return cache[key]

        
        # 1. Base List Discovery (Very Fast)
        disc_url = f"{self.anypoint_url}/armui/api/v2/applications"
        try:
            res = self.http_session.get(disc_url, headers=headers, timeout=15)
            
            # Handle 401 Unauthorized (Expired Token)
            if res.status_code == 401:
                if self.using_bearer_override:
                    raise MuleSoftAuthError("Bearer Token Expired")
                log.warning("MuleSoft session expired. Re-authenticating...")
                self.access_token = None
                headers = self.get_headers() # Triggers re-auth
                headers.update({ "X-ANYPNT-ORG-ID": org_id, "X-ANYPNT-ENV-ID": env_id })
                res = self.http_session.get(disc_url, headers=headers, timeout=15)

            if res.status_code != 200:
                log.error(f"Discovery Failed: {res.status_code} - {res.text}")
                return []
                
            apps = res.json().get('data', [])
        except Exception as e:
            log.error(f"App Discovery Error: {e}")
            return []

        if not extract_details or not apps:
            return apps

        # 2. Parallel Deep Scan (Bounded Workers)
        def enrich(app):
            try:
                target = app.get('target', {}).get('type', '')
                app_id = app.get('id')
                
                # CloudHub 2.0 / RTF Path
                if target in ["MC", "RTF"]:
                    d_url = f"{self.anypoint_url}/amc/adam/api/organizations/{org_id}/environments/{env_id}/deployments/{app_id}"
                    d_res = self.http_session.get(d_url, headers=headers, timeout=5)
                    if d_res.status_code == 200:
                        app['adam_details'] = d_res.json()
                        
                # CloudHub 1.0 Path
                else:
                    domain = (app.get('domain') or app.get('name', '')).split('.cloudhub.io')[0]
                    ch1_url = f"{self.anypoint_url}/cloudhub/api/v2/applications/{domain}"
                    d_res = self.http_session.get(ch1_url, headers=headers, timeout=5)
                    if d_res.status_code == 200:
                        app.update(d_res.json())
            except Exception: pass
            return app

        def process_apps_parallel(apps_to_process):
            results = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_app = {executor.submit(enrich, app): app for app in apps_to_process}
                for future in as_completed(future_to_app):
                    try:
                        results.append(future.result())
                    except Exception:
                        results.append(future_to_app[future])
            return results

        # Process apps in parallel (bounded)
        apps = process_apps_parallel(apps)

        # 3. Clean Minimum Payload Pruning
        pruned_apps = [self._prune_app(a) for a in apps]
        cache[key] = pruned_apps
        return pruned_apps

    def _prune_app(self, a):
        """Strip the world, return only version essence."""
        # Hunt for a valid Name/Domain across all possible sources
        name = a.get("name") or a.get("fullDomain") or a.get("domain")
        if not name and a.get("adam_details"):
            # Fallback to AMC detail name
            name = a["adam_details"].get("name")
        if not name:
            # Final fallback to common nesting
            name = a.get("artifact", {}).get("name") or a.get("application", {}).get("name", "Unknown App")

        v = None
        if a.get('adam_details'):
            v = a['adam_details'].get('application', {}).get('ref', {}).get('version')
        
        return {
            "id": a.get("id"),
            "name": name,
            "fullDomain": name, # Ensure JS finds it in either property
            "muleVersion": a.get("muleVersion"),
            "appVersion": v or a.get("filename") or a.get("fileName") or "Unknown Artifact",
            "targetType": a.get("target", {}).get("type")
        }

    def change_app_status(self, org_id, env_id, app_data, action):
        """action is 'START' or 'STOP'"""
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        target_type = app_data.get('targetType') or app_data.get('target', {}).get('type', 'Unknown')
        app_id = app_data.get('id')
        app_domain = app_data.get('fullDomain') or app_data.get('name') or (app_data.get('artifact', {}).get('name'))
        
        try:
            if target_type in ["MC", "RTF"]:
                # CloudHub 2.0 / AMC Architecture
                target_state = "STARTED" if action == "START" else "STOPPED"
                url = f"{self.anypoint_url}/amc/application-manager/api/v2/organizations/{org_id}/environments/{env_id}/deployments/{app_id}"
                payload = {"application": {"desiredState": target_state}}
                res = self.http_session.patch(url, headers=headers, json=payload)
                if res.status_code in [200, 202, 204]:
                    log.info(f"Triggered {action} for AMC App {app_id}")
                    return True, ""
                return False, res.text
            else:
                # CloudHub 1.0 Legacy Architecture
                target_state = "start" if action == "START" else "stop"
                domain = app_domain if app_domain else app_id
                url = f"{self.anypoint_url}/cloudhub/api/v2/applications/{domain}/status"
                payload = {"status": target_state}
                res = self.http_session.post(url, headers=headers, json=payload)
                if res.status_code in [200, 202, 204]:
                    log.info(f"Triggered {action} for CH1 App {domain}")
                    return True, ""
                return False, res.text
        except Exception as e:
            log.error(f"Failed to execute app action '{action}': {e}")
            return False, str(e)