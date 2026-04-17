import os
import base64
import requests
from dotenv import load_dotenv

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
        b64_auth = base64.encodebytes(auth_str.encode()).decode().replace('\n', '')
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
                    "project": r['project']['name']
                } 
                for r in repos if r['name'].startswith(prefix)
            ]
        return []

    def get_branches(self, repo_name):
        url = f"{self.base_url}/git/repositories/{repo_name}/refs?filter=heads/&api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [ref['name'].replace('refs/heads/', '') for ref in response.json().get('value', [])]
        return ["main", "develop", "dev", "qa", "staging", "pre-prod"]

    def get_commit_details(self, repo_name, source, target):
        """
        Uses Azure Git Diffs API to compare branches.
        URL: GET .../diffs/commits?baseVersion={target}&targetVersion={source}
        """
        url = f"{self.base_url}/git/repositories/{repo_name}/diffs/commits"
        params = {
            "baseVersion": target,
            "baseVersionType": "branch",
            "targetVersion": source,
            "targetVersionType": "branch",
            "api-version": "7.1"
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            # Extract commits and file paths
            commits = [{"message": c['comment'], "author": c['author']['name']} for c in data.get('commits', [])]
            # Changes list gives us file paths
            files = list(set([change['item']['path'] for change in data.get('changes', []) if 'item' in change]))
            return {
                "commits": commits[:10], # Limit to last 10 for UI cleaniness
                "files": [f.split('/')[-1] for f in files[:15]], # Show filenames only
                "aheadCount": data.get('aheadCount', 0)
            }
        return {"commits": [], "files": [], "aheadCount": 0, "error": "Branches might not exist or no diff found."}

    def create_pull_request(self, repo_name, from_branch, to_branch):
        url = f"{self.base_url}/git/repositories/{repo_name}/pullrequests?api-version=7.1"
        payload = {
            "sourceRefName": f"refs/heads/{from_branch}",
            "targetRefName": f"refs/heads/{to_branch}",
            "title": f"Beyond Native Bulk PR: {from_branch} -> {to_branch}",
            "description": "Automated Pull Request raised via Beyond Native Suite."
        }
        response = requests.post(url, headers=self.headers, json=payload)
        return response.status_code, response.json()