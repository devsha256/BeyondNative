from flask import Flask, render_template, request, jsonify, redirect
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
devops = AzureDevOpsManager()
mule = MuleSoftManager()

# --- Common Routes ---
@app.route('/')
def index():
    return render_template('devops/discovery.html')

# --- DevOps Suite ---
@app.route('/devops/bulk-pr')
def bulk_pr_view():
    return render_template('devops/bulk_pr.html')

# --- MuleSoft Suite ---
@app.route('/mulesoft')
def mulesoft_index():
    return render_template('mulesoft/index.html')

@app.route('/mulesoft/runtime-control')
def runtime_control():
    return render_template('mulesoft/runtime_control.html')

@app.route('/mulesoft/version-comparator')
def version_comparator():
    return render_template('mulesoft/version_comparator.html')

@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    cookie = request.json.get('cookie')
    mule.set_session(cookie)
    return jsonify({"status": "Session Updated"})

@app.route('/api/mule/apps', methods=['POST'])
def get_mule_apps():
    data = request.json
    apps = mule.get_runtime_apps(data['org_id'], data['env_id'])
    return jsonify(apps)

# --- Existing DevOps APIs (Full Content) ---
@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    repos = devops.get_repositories(prefix)
    return jsonify({"repositories": repos})

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    branches = devops.get_branches(repo_name)
    return jsonify(branches)

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    repo_name = request.args.get('repo')
    source = request.args.get('source', 'develop')
    target = request.args.get('target', 'main')
    details = devops.get_commit_details(repo_name, source, target)
    return jsonify(details)

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    data = request.json
    status, result = devops.create_pull_request(data['repo_id'], data['from_branch'], data['to_branch'], data.get('last_msg', 'Manual Trigger'))
    return jsonify({"status": status, "result": result})

@app.route('/api/bulk-create-pr', methods=['POST'])
def bulk_create_pr():
    data = request.json
    operations = data.get('operations', [])
    def run_op(op):
        status, res = devops.create_pull_request(op['repo_id'], op['from_branch'], op['to_branch'], op.get('last_msg', 'Bulk Deployment'))
        return {"repo": op['repo_id'], "status": status, "details": res}
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(run_op, operations))
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)