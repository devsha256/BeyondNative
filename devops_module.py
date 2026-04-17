import os
import base64
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

class AzureDevOpsManager:
    def __init__(self):
        self.org = os.getenv("AZURE_ORG")
        self.project = os.getenv("AZURE_PROJECT")
        self.pat = os.getenv("AZURE_PAT")
        self.base_url = f"https://dev.azure.com/{self.org}/{self.project}/_apis"
        self.headers = self._get_headers()

    def _get_headers(self):
        auth_str = f":{self.pat}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/json"
        }

    def get_repositories(self, prefix=""):
        url = f"{self.base_url}/git/repositories?api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            repos = response.json().get('value', [])
            return [
                {
                    "name": r['name'],
                    "url": r['webUrl'],
                    "project": r['project']['name'],
                    "id": r['id']
                } 
                for r in repos if r['name'].startswith(prefix)
            ]
        return []

    def get_branches(self, repo_id):
        url = f"{self.base_url}/git/repositories/{repo_id}/refs?filter=heads/&api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [ref['name'].replace('refs/heads/', '') for ref in response.json().get('value', [])]
        return ["main", "develop"] # Fallback

    def create_pull_request(self, repo_id, from_branch, to_branch):
        url = f"{self.base_url}/git/repositories/{repo_id}/pullrequests?api-version=7.1"
        payload = {
            "sourceRefName": f"refs/heads/{from_branch}",
            "targetRefName": f"refs/heads/{to_branch}",
            "title": f"Beyond Native Bulk PR: {from_branch} -> {to_branch}",
            "description": "Automated Pull Request raised via Beyond Native Suite."
        }
        response = requests.post(url, headers=self.headers, json=payload)
        return response.status_code, response.json()

    def get_commit_details(self, repo_name):
        # For now, we return mock data to ensure the UI works. 
        # Later, replace this with actual Azure API calls.
        return {
            "commits": [
                {"message": "Merged feature/auth", "author": "John Doe"},
                {"message": "Fix: null pointer in logger", "author": "Jane Smith"}
            ],
            "files": ["app.py", "styles.css", "init.sql"]
        }