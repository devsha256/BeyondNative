from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)
devops = AzureDevOpsManager()
mule = MuleSoftManager()

# --- Common/Home ---
@app.route('/')
def home():
    return render_template('index.html')

# --- DevOps Suite ---
@app.route('/devops')
def devops_index():
    return render_template('devops/index.html')

@app.route('/devops/discovery')
def devops_discovery():
    return render_template('devops/discovery.html')

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

# --- Shared APIs ---
@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    data = request.json
    if data and 'cookie' in data:
        mule.set_session(data['cookie'])
    return jsonify({"status": "success", "message": "Session Synced"})

@app.route('/api/mule/apps', methods=['POST'])
def get_mule_apps():
    data = request.json
    apps = mule.get_runtime_apps(data['org_id'], data['env_id'])
    return jsonify(apps)

@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    return jsonify({"repositories": devops.get_repositories(prefix)})

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    return jsonify(devops.get_branches(repo_name))

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    repo = request.args.get('repo')
    source = request.args.get('source', 'develop')
    target = request.args.get('target', 'main')
    return jsonify(devops.get_commit_details(repo, source, target))

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    data = request.json
    status, result = devops.create_pull_request(data['repo_id'], data['from_branch'], data['to_branch'], data.get('last_msg'))
    return jsonify({"status": status, "result": result})

if __name__ == '__main__':
    app.run(debug=True)