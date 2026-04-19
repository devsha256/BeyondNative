import os
import requests
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import db_utils
from logger import log

load_dotenv()

from requests.adapters import HTTPAdapter

class MuleSoftManager:
    def __init__(self):
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.session_cookie = None
        self.xsrf_token = None
        self.access_token = None
        
        # Enable connection pooling to dramatically reduce TLS handshake / TCP overhead
        self.http_session = requests.Session()
        adapter = HTTPAdapter(pool_connections=300, pool_maxsize=300)
        self.http_session.mount('https://', adapter)
        self.http_session.mount('http://', adapter)

    def authenticate_from_db(self):
        bearer = db_utils.get_setting('mule_bearer')
        if bearer:
            self.access_token = bearer.replace('Bearer ', '').strip()
            return True

        client_id = db_utils.get_setting('mule_client_id')
        client_secret = db_utils.get_setting('mule_client_secret')
        if client_id and client_secret:
            try:
                res = self.http_session.post(
                    f"{self.anypoint_url}/accounts/api/v2/oauth2/token", 
                    data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"}
                )
                if res.status_code == 200:
                    self.access_token = res.json().get('access_token')
                    return True
            except: pass
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
            log.debug(f"MuleSoft Org Fetch Status (me): {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                if 'user' in data:
                    return data.get('user', {}).get('memberOfOrganizations', [])
                elif 'memberOfOrganizations' in data:
                    return data.get('memberOfOrganizations', [])
            else:
                log.warning(f"'/me' failed with {res.status_code}. Attempting Connected App fallback to '/organizations'...")
                res_orgs = self.http_session.get(url_orgs, headers=self.get_headers())
                log.debug(f"MuleSoft Org Fetch Status (orgs): {res_orgs.status_code}")
                if res_orgs.status_code == 200:
                    data_orgs = res_orgs.json()
                    if isinstance(data_orgs, list): return data_orgs
                    if 'data' in data_orgs: return data_orgs.get('data', [])
                    return [data_orgs]
                else:
                    log.error(f"Fallback Fetch Response: {res_orgs.text[:500]}")
            return []
        except Exception as e:
            log.error(f"MuleSoft Org Fetch Error: {e}")
            return []

    def get_environments(self, org_id):
        """Fetches environments for the specific organization."""
        url = f"{self.anypoint_url}/accounts/api/organizations/{org_id}/environments"
        try:
            res = self.http_session.get(url, headers=self.get_headers())
            if res.status_code == 200:
                return res.json().get('data', [])
        except Exception as e:
            log.error(f"MuleSoft Env Fetch Error: {e}")
        return []

    def get_app_details(self, org_id, env_id, app_id):
        """Fetches deep details from the ADAM api for AMC deployments"""
        # Minimal headers required for details API
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.access_token}" if self.access_token else ""
        }
        url = f"{self.anypoint_url}/amc/adam/api/organizations/{org_id}/environments/{env_id}/deployments/{app_id}"
        try:
            res = self.http_session.get(url, headers=headers)
            if res.status_code == 200:
                return res.json()
        except:
            pass
        return None

    def get_runtime_apps(self, org_id, env_id, extract_details=False):
        """Fetches all types of applications from Runtime Manager ARMUI."""
        url = f"{self.anypoint_url}/armui/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        apps = []
        try:
            res = self.http_session.get(url, headers=headers)
            if res.status_code == 200:
                body = res.json()
                apps = body.get('data', []) if 'data' in body else (body if isinstance(body, list) else [])
            else:
                log.error(f"App Fetch Failed: {res.status_code} - {res.text}")
        except Exception as e:
            log.error(f"MuleSoft App Fetch Error: {e}")
            return []

        if extract_details and apps:
            # 1. Bulk extraction for CH1 (99% chance of getting version here)
            ch1_bulk = {}
            try:
                ch1_res = self.http_session.get(f"{self.anypoint_url}/cloudhub/api/v2/applications", headers=headers, timeout=5)
                if ch1_res.status_code == 200:
                    for a in ch1_res.json():
                        if a.get('domain'): ch1_bulk[a['domain']] = a
            except Exception: pass

            # 2. Bulk extraction for AMC (90% chance of getting version here)
            amc_bulk = {}
            try:
                amc_bulk_url = f"{self.anypoint_url}/amc/application-manager/api/v2/organizations/{org_id}/environments/{env_id}/deployments"
                amc_res = self.http_session.get(amc_bulk_url, headers=headers, timeout=5)
                if amc_res.status_code == 200:
                    for item in amc_res.json().get('items', []):
                        if item.get('id'): amc_bulk[item['id']] = item
            except Exception: pass

            # 3. Targeted Parallel Fallback for strictly missing details
            def resolve_remaining(app):
                try:
                    target_type = app.get('target', {}).get('type', 'Unknown')
                    app_id = app.get('id')
                    
                    # Already got AMC version from bulk?
                    if target_type in ["MC", "RTF"] and app_id in amc_bulk:
                        # Only use bulk if it has the version payload
                        if amc_bulk[app_id].get('application', {}).get('ref'):
                            app['adam_details'] = amc_bulk[app_id]
                            return app

                    # Already got CH1 version from bulk?
                    domain = app.get('domain') or app.get('name')
                    if target_type not in ["MC", "RTF"] and domain:
                        clean_domain = domain.split('.cloudhub.io')[0] if '.cloudhub.io' in domain else domain
                        if clean_domain in ch1_bulk:
                            app.update({k: v for k, v in ch1_bulk[clean_domain].items() if v is not None})
                            if app.get('filename'): return app

                    # FALLBACK: Surgical individual fetch if bulk missed it
                    if target_type in ["MC", "RTF"] and app_id:
                        details = self.get_app_details(org_id, env_id, app_id)
                        if details: app['adam_details'] = details
                    elif domain:
                        clean_domain = domain.split('.cloudhub.io')[0] if '.cloudhub.io' in domain else domain
                        d_res = self.http_session.get(f"{self.anypoint_url}/cloudhub/api/v2/applications/{clean_domain}", headers=headers, timeout=5)
                        if d_res.status_code == 200: app.update(d_res.json())
                except Exception: pass
                return app

            # Only thread apps that don't have enough metadata yet
            with ThreadPoolExecutor(max_workers=50) as executor:
                apps = list(executor.map(resolve_remaining, apps))

        # Final Pruning: Only return the minimum required keys to reduce payload size
        pruned_apps = []
        for a in apps:
            p = {
                "id": a.get("id"),
                "name": a.get("name"),
                "domain": a.get("domain"),
                "fullDomain": a.get("fullDomain"),
                "muleVersion": a.get("muleVersion"),
                "filename": a.get("filename") or a.get("fileName"),
                "target": a.get("target"),
                "application": a.get("application") # CH2 summary might have version info here
            }
            if a.get("adam_details"):
                # Drill down to only the semver ref in adam_details
                ref = a["adam_details"].get("application", {}).get("ref")
                if ref:
                    p["adam_details"] = {"application": {"ref": ref}}
            pruned_apps.append(p)
        
        return pruned_apps

    def change_app_status(self, org_id, env_id, app_data, action):
        """action is 'START' or 'STOP'"""
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        target_type = app_data.get('target', {}).get('type', 'Unknown')
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