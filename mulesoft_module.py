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