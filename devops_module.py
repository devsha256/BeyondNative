import os
import base64
import requests
import fnmatch
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
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/json"
        }

    def get_repositories(self, pattern=""):
        url = f"{self.base_url}/git/repositories?api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            repos = response.json().get('value', [])
            
            # If no wildcard characters are present, treat it as a prefix search by appending '*'
            if pattern and '*' not in pattern and '?' not in pattern:
                pattern = f"{pattern}*"
                
            return [
                {
                    "name": r['name'],
                    "url": r['webUrl'],
                    "project": r['project']['name']
                } 
                for r in repos if not pattern or fnmatch.fnmatch(r['name'], pattern)
            ]
        return []

    def get_repository(self, repo_name):
        url = f"{self.base_url}/git/repositories/{repo_name}?api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            r = response.json()
            return {
                "name": r['name'],
                "url": r['webUrl'],
                "project": r['project']['name']
            }
        return None

    def get_branches(self, repo_name):
        url = f"{self.base_url}/git/repositories/{repo_name}/refs?filter=heads/&api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [ref['name'].replace('refs/heads/', '') for ref in response.json().get('value', [])]
        return ["main", "develop", "dev", "qa", "staging", "pre-prod"]

    def get_commit_details(self, repo_name, source, target):
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
            commits_raw = data.get('commits', [])
            commits = [{"message": c['comment'], "author": c['author']['name']} for c in commits_raw]
            last_msg = commits[0]['message'] if commits else "No new commits"
            files = list(set([change['item']['path'] for change in data.get('changes', []) if 'item' in change]))
            return {
                "commits": commits[:10],
                "files": [f.split('/')[-1] for f in files[:15]],
                "aheadCount": data.get('aheadCount', 0),
                "last_commit_message": last_msg
            }
        return {"commits": [], "files": [], "aheadCount": 0, "last_commit_message": "N/A"}

    def create_pull_request(self, repo_name, from_branch, to_branch, last_msg):
        url = f"{self.base_url}/git/repositories/{repo_name}/pullrequests?api-version=7.1"
        pr_title = f"{to_branch} Deployment: {last_msg}"
        payload = {
            "sourceRefName": f"refs/heads/{from_branch}",
            "targetRefName": f"refs/heads/{to_branch}",
            "title": pr_title,
            "description": f"Automated Deployment PR for {repo_name}."
        }
        response = requests.post(url, headers=self.headers, json=payload)
        return response.status_code, response.json()