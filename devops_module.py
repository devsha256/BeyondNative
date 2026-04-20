import os
import base64
import requests
import fnmatch
import urllib.parse
from dotenv import load_dotenv
import db_utils

load_dotenv()

class AzureDevOpsManager:
    def __init__(self):
        # We prefer DB settings to allow real-time updates via settings page
        self.org = db_utils.get_setting('azure_org') or os.getenv("AZURE_ORG")
        self.project = db_utils.get_setting('azure_project') or os.getenv("AZURE_PROJECT")
        self.pat = db_utils.get_setting('azure_pat') or os.getenv("AZURE_PAT")
        self.identity_id = None # Cache for auto-complete identity
        self.base_url = f"https://dev.azure.com/{self.org}/{self.project}/_apis"
        self.headers = self._get_headers()

    def check_connection(self):
        if not self.pat or not self.org:
            return False
        # Use a lightweight API to check auth
        url = f"https://dev.azure.com/{self.org}/_apis/projects?api-version=7.1"
        try:
            res = requests.get(url, headers=self.headers, timeout=5)
            return res.status_code == 200
        except:
            return False

    def _get_headers(self):
        auth_str = f":{self.pat}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/json"
        }

    def _get_identity_id(self):
        if self.identity_id: return self.identity_id
        url = f"https://dev.azure.com/{self.org}/_apis/connectionData"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                self.identity_id = res.json().get('authenticatedUser', {}).get('id')
                return self.identity_id
        except: pass
        return None

    def get_repositories(self, pattern=""):
        url = f"{self.base_url}/git/repositories?api-version=7.1"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            repos = response.json().get('value', [])
            
            if not pattern:
                return [{"name": r['name'], "url": r['webUrl'], "project": r['project']['name']} for r in repos]
            
            # If no wildcard characters are present, treat it as a prefix search by appending '*'
            if '*' not in pattern and '?' not in pattern:
                pattern = f"{pattern}*"
                
            pattern_lower = pattern.lower()
            return [
                {
                    "name": r['name'],
                    "url": r['webUrl'],
                    "project": r['project']['name']
                } 
                for r in repos if fnmatch.fnmatch(r['name'].lower(), pattern_lower)
            ]
        return []

    def get_repository(self, repo_name):
        encoded_name = urllib.parse.quote(repo_name)
        url = f"{self.base_url}/git/repositories/{encoded_name}?api-version=7.1"
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

    def create_pull_request(self, repo_name, from_branch, to_branch, last_msg, auto_complete=False):
        url = f"{self.base_url}/git/repositories/{repo_name}/pullrequests?api-version=7.1"
        pr_title = f"{to_branch} Deployment: {last_msg}"
        payload = {
            "sourceRefName": f"refs/heads/{from_branch}",
            "targetRefName": f"refs/heads/{to_branch}",
            "title": pr_title,
            "description": f"Automated Deployment PR for {repo_name}."
        }

        if auto_complete:
            id_val = self._get_identity_id()
            if id_val:
                payload["autoCompleteSetBy"] = {"id": id_val}
                payload["completionOptions"] = {
                    "deleteSourceBranch": False,
                    "mergeStrategy": "squash", # Common for automated deployments
                    "transitionWorkItems": True
                }

        response = requests.post(url, headers=self.headers, json=payload)
        data = response.json()
        if response.status_code in [200, 201]:
            pr_id = data.get('pullRequestId')
            # Manually construct the definitive web URL for browser viewing
            data['webUrl'] = f"https://dev.azure.com/{self.org}/{self.project}/_git/{repo_name}/pullrequest/{pr_id}"
        return response.status_code, data