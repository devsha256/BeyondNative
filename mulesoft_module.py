import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MuleSoftManager:
    def __init__(self):
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.session_cookie = None
        # You can store the vanity URL in .env
        self.vanity_url = os.getenv("ANYPOINT_VANITY_URL", "https://anypoint.mulesoft.com/login/domain")

    def set_session(self, cookie):
        self.session_cookie = cookie

    def get_headers(self):
        return {
            "Cookie": self.session_cookie,
            "Content-Type": "application/json"
        }

    def get_organizations(self):
        """Fetches the user's organization and environment details."""
        url = f"{self.anypoint_url}/accounts/api/me"
        res = requests.get(url, headers=self.get_headers())
        return res.json() if res.status_code == 200 else None

    def get_runtime_apps(self, org_id, env_id):
        """Fetches apps from Runtime Manager."""
        url = f"{self.anypoint_url}/cloudhub/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        res = requests.get(url, headers=headers)
        return res.json() if res.status_code == 200 else []

    def manage_app_status(self, org_id, env_id, app_name, action):
        """Action: START / STOP"""
        url = f"{self.anypoint_url}/cloudhub/api/v2/applications/{app_name}/status"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        payload = {"status": action}
        res = requests.post(url, headers=headers, json=payload)
        return res.status_code