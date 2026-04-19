from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager
from concurrent.futures import ThreadPoolExecutor
import db_utils

db_utils.init_db()

app = Flask(__name__)
CORS(app) 

devops = AzureDevOpsManager()
mule = MuleSoftManager()

# --- Navigation ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/devops')
def devops_index():
    return render_template('devops/index.html')


@app.route('/devops/bulk-pr')
def bulk_pr_view():
    return render_template('devops/bulk_pr.html')

@app.route('/mulesoft')
def mulesoft_index():
    return render_template('mulesoft/index.html')

@app.route('/mulesoft/runtime-control')
def runtime_control():
    return render_template('mulesoft/runtime_control.html')

@app.route('/mulesoft/version-comparator')
def version_comparator():
    return render_template('mulesoft/version_comparator.html')

# --- Azure DevOps APIs ---
@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    return jsonify({"repositories": devops.get_repositories(prefix)})

@app.route('/api/extract-by-file', methods=['POST'])
def extract_by_file():
    repo_names = request.json.get('repos', [])
    matched = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(devops.get_repository, repo_names)
        for r in results:
            if r:
                matched.append(r)
    return jsonify({"repositories": matched})

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    return jsonify(devops.get_branches(repo_name))

@app.route('/api/bulk-branches', methods=['POST'])
def bulk_get_branches():
    repo_names = request.json.get('repos', [])
    def fetch_branches(repo_name):
        return {
            "name": repo_name,
            "branches": devops.get_branches(repo_name)
        }
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(fetch_branches, repo_names))
    return jsonify(results)

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    repo = request.args.get('repo')
    source = request.args.get('source', 'develop')
    target = request.args.get('target', 'main')
    return jsonify(devops.get_commit_details(repo, source, target))

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    data = request.json
    status, result = devops.create_pull_request(
        data['repo_id'], data['from_branch'], data['to_branch'], data.get('last_msg')
    )
    return jsonify({"status": status, "result": result})

@app.route('/api/bulk-create-pr', methods=['POST'])
def bulk_create_pr():
    data = request.json
    operations = data.get('operations', [])
    def run_op(op):
        status, res = devops.create_pull_request(
            op['repo_id'], op['from_branch'], op['to_branch'], op.get('last_msg')
        )
        return {"repo": op['repo_id'], "status": status, "details": res}
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(run_op, operations))
    return jsonify(results)

# --- MuleSoft APIs ---
@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    data = request.json
    if data and 'curl' in data:
        success = mule.set_session(data['curl'])
        if success:
            return jsonify({"status": "success", "message": "Session Synced from cURL!"})
        return jsonify({"status": "error", "message": "Failed to extract required tokens from cURL string"}), 400
    return jsonify({"status": "error", "message": "No curl string provided"}), 400

@app.route('/settings')
def settings_page():
    keys = ['azure_org', 'azure_project', 'azure_pat', 'mule_client_id', 'mule_client_secret', 'mule_bearer']
    setting_vals = {k: db_utils.get_setting(k) for k in keys}
    return render_template('settings.html', settings=setting_vals)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    if not data: return jsonify({"error": "No data"}), 400
    for k, v in data.items():
        db_utils.set_setting(k, v)
    return jsonify({"status": "success", "message": "Settings updated safely in sqlite3 DB!"})

@app.route('/api/mule/orgs', methods=['GET'])
def get_mule_orgs():
    return jsonify(mule.get_organizations())

@app.route('/api/mule/envs/<org_id>', methods=['GET'])
def get_mule_envs(org_id):
    return jsonify(mule.get_environments(org_id))

@app.route('/api/mule/apps', methods=['POST'])
def get_mule_apps():
    data = request.json
    org_id = data.get('org_id')
    env_id = data.get('env_id')
    return jsonify(mule.get_runtime_apps(org_id, env_id))

@app.route('/api/mule/app-action', methods=['POST'])
def change_mule_app_status():
    data = request.json
    org_id = data.get('org_id')
    env_id = data.get('env_id')
    app_data = data.get('app')
    action = data.get('action') # 'START' or 'STOP'
    
    success, msg = mule.change_app_status(org_id, env_id, app_data, action)
    if success:
        return jsonify({"status": "success", "message": f"Successfully triggered {action}"})
    return jsonify({"status": "error", "message": msg}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5001)