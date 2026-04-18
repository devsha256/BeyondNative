import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MuleSoftManager:
    def __init__(self):
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.session_cookie = None

    def set_session(self, cookie):
        self.session_cookie = cookie

    def get_headers(self):
        return {
            "Cookie": self.session_cookie,
            "Content-Type": "application/json"
        }

    def get_organizations(self):
        """Fetches all organizations the user has access to."""
        url = f"{self.anypoint_url}/accounts/api/me"
        try:
            res = requests.get(url, headers=self.get_headers())
            if res.status_code == 200:
                data = res.json()
                # Extracting the master org and any sub-organizations
                user_obj = data.get('user', {})
                member_groups = user_obj.get('memberOfOrganizations', [])
                return member_groups
            return []
        except:
            return []

    def get_environments(self, org_id):
        """Fetches environments for a specific organization ID."""
        url = f"{self.anypoint_url}/accounts/api/organizations/{org_id}/environments"
        try:
            res = requests.get(url, headers=self.get_headers())
            return res.json().get('data', []) if res.status_code == 200 else []
        except:
            return []

    def get_runtime_apps(self, org_id, env_id):
        url = f"{self.anypoint_url}/cloudhub/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        try:
            res = requests.get(url, headers=headers)
            return res.json() if res.status_code == 200 else []
        except:
            return []