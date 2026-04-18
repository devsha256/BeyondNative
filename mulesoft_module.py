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
            "Cookie": self.session_cookie if self.session_cookie else "",
            "Content-Type": "application/json"
        }

    def get_organizations(self):
        """Fetches the user profile which contains the list of organizations."""
        url = f"{self.anypoint_url}/accounts/api/me"
        try:
            res = requests.get(url, headers=self.get_headers())
            if res.status_code == 200:
                data = res.json()
                # Accessing memberOfOrganizations which holds the Business Groups
                return data.get('user', {}).get('memberOfOrganizations', [])
            return []
        except Exception as e:
            print(f"MuleSoft Org Fetch Error: {e}")
            return []

    def get_environments(self, org_id):
        """Fetches environments for the specific organization."""
        url = f"{self.anypoint_url}/accounts/api/organizations/{org_id}/environments"
        try:
            res = requests.get(url, headers=self.get_headers())
            if res.status_code == 200:
                return res.json().get('data', [])
            return []
        except Exception as e:
            print(f"MuleSoft Env Fetch Error: {e}")
            return []

    def get_runtime_apps(self, org_id, env_id):
        """Fetches applications from Runtime Manager."""
        url = f"{self.anypoint_url}/cloudhub/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                return res.json()
            return []
        except Exception as e:
            print(f"MuleSoft App Fetch Error: {e}")
            return []