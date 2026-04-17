import os
import base64
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

app = Flask(__name__)

# Configuration from .env or Direct
AZURE_ORG = os.getenv("AZURE_ORG")
AZURE_PROJECT = os.getenv("AZURE_PROJECT")
PAT = os.getenv("AZURE_PAT")

def get_auth_header():
    auth_str = f":{PAT}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    return {"Authorization": f"Basic {b64_auth}", "Content-Type": "application/json"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    url = f"https://dev.azure.com/{AZURE_ORG}/{AZURE_PROJECT}/_apis/git/repositories?api-version=7.1"
    response = requests.get(url, headers=get_auth_header())
    
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch repos"}), 400
    
    repos = [r['name'] for r in response.json()['value'] if r['name'].startswith(prefix)]
    return jsonify({"repositories": repos})

def create_single_pr(repo_name, from_branch, to_branch):
    url = f"https://dev.azure.com/{AZURE_ORG}/{AZURE_PROJECT}/_apis/git/repositories/{repo_name}/pullrequests?api-version=7.1"
    payload = {
        "sourceRefName": f"refs/heads/{from_branch}",
        "targetRefName": f"refs/heads/{to_branch}",
        "title": f"Bulk PR: {from_branch} -> {to_branch}",
        "description": "Automated via Python Flask Suite"
    }
    res = requests.post(url, headers=get_auth_header(), json=payload)
    return {"repo": repo_name, "status": res.status_code, "data": res.json()}

@app.route('/api/bulk-pr', methods=['POST'])
def bulk_pr():
    data = request.json
    repos = data.get('repositories', [])
    from_b = data.get('from_branch')
    to_b = data.get('to_branch')

    # Fire 30-40 requests in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda r: create_single_pr(r, from_b, to_b), repos))
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)