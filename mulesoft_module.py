import os
import requests
from dotenv import load_dotenv

load_dotenv()

class MuleSoftManager:
    def __init__(self):
        self.anypoint_url = "https://anypoint.mulesoft.com"
        self.session_cookie = None

    def set_session(self, cookie):
        """Stores the raw cookie string for subsequent REST calls."""
        self.session_cookie = cookie

    def get_headers(self):
        """Generates the necessary headers including the session cookie."""
        return {
            "Cookie": self.session_cookie,
            "Content-Type": "application/json"
        }

    def get_runtime_apps(self, org_id, env_id):
        """Fetches apps from Runtime Manager using the stored session."""
        url = f"{self.anypoint_url}/cloudhub/api/v2/applications"
        headers = self.get_headers()
        headers["X-ANYPNT-ORG-ID"] = org_id
        headers["X-ANYPNT-ENV-ID"] = env_id
        
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                return res.json()
            return {"error": f"Anypoint returned status {res.status_code}"}
        except Exception as e:
            return {"error": str(e)}