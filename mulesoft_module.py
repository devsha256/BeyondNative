import os
import requests
import concurrent.futures
from dotenv import load_dotenv
import db_utils
from logger import log

load_dotenv()

class MuleSoftManager:
    def __init__(self):
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.session_cookie = None
        self.xsrf_token = None
        self.access_token = None

    def authenticate_from_db(self):
        bearer = db_utils.get_setting('mule_bearer')
        if bearer:
            self.access_token = bearer.replace('Bearer ', '').strip()
            return True

        client_id = db_utils.get_setting('mule_client_id')
        client_secret = db_utils.get_setting('mule_client_secret')
        if client_id and client_secret:
            try:
                res = requests.post(
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
            res = requests.get(url_me, headers=self.get_headers())
            log.debug(f"MuleSoft Org Fetch Status (me): {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                if 'user' in data:
                    return data.get('user', {}).get('memberOfOrganizations', [])
                elif 'memberOfOrganizations' in data:
                    return data.get('memberOfOrganizations', [])
            else:
                log.warning(f"'/me' failed with {res.status_code}. Attempting Connected App fallback to '/organizations'...")
                res_orgs = requests.get(url_orgs, headers=self.get_headers())
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
            res = requests.get(url, headers=self.get_headers())
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
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                return res.json()
        except:
            pass
        return None

    def get_runtime_apps(self, org_id, env_id, extract_details=False):
        """Fetches applications from Runtime Manager."""
        url = f"{self.anypoint_url}/armui/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        apps = []
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                body = res.json()
                apps = body.get('data', []) if 'data' in body else (body if isinstance(body, list) else [])
        except Exception as e:
            log.error(f"MuleSoft App Fetch Error: {e}")
            return []
            
        # Parallel Enrichment for CloudHub 2.0 / AMC metadata
        if apps and extract_details:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_app = {}
                for app in apps:
                    app_id = app.get('id')
                    target_type = app.get('target', {}).get('type', 'Unknown')
                    if target_type in ["MC", "RTF"] and app_id:
                        future_to_app[executor.submit(self.get_app_details, org_id, env_id, app_id)] = app
                
                for future in concurrent.futures.as_completed(future_to_app):
                    app = future_to_app[future]
                    try:
                        details = future.result()
                        if details:
                            app['adam_details'] = details
                    except:
                        pass
        return apps

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
                res = requests.patch(url, headers=headers, json=payload)
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
                res = requests.post(url, headers=headers, json=payload)
                if res.status_code in [200, 202, 204]:
                    log.info(f"Triggered {action} for CH1 App {domain}")
                    return True, ""
                return False, res.text
        except Exception as e:
            log.error(f"Failed to execute app action '{action}': {e}")
            return False, str(e)