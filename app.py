from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager
from concurrent.futures import ThreadPoolExecutor

# Initialize Flask with CORS enabled for the Bookmarklet sync
app = Flask(__name__)
CORS(app) 

# Initialize managers
devops = AzureDevOpsManager()
mule = MuleSoftManager()

# --- 1. Global / Home Routes ---
@app.route('/')
def home():
    """Main landing page redirecting to DevOps Discovery by default."""
    return render_template('devops/discovery.html')

# --- 2. DevOps Suite Routes ---
@app.route('/devops')
def devops_index():
    """DevOps Suite Dashboard."""
    return render_template('devops/index.html')

@app.route('/devops/discovery')
def devops_discovery():
    """Repository search and selection."""
    return render_template('devops/discovery.html')

@app.route('/devops/bulk-pr')
def bulk_pr_view():
    """Bulk PR configuration and execution."""
    return render_template('devops/bulk_pr.html')

# --- 3. MuleSoft Suite Routes ---
@app.route('/mulesoft')
def mulesoft_index():
    """MuleSoft Suite Dashboard."""
    return render_template('mulesoft/index.html')

@app.route('/mulesoft/runtime-control')
def runtime_control():
    """Start/Stop Apps with dynamic Org/Env discovery."""
    return render_template('mulesoft/runtime_control.html')

@app.route('/mulesoft/version-comparator')
def version_comparator():
    """Compare runtime/app versions across environments."""
    return render_template('mulesoft/version_comparator.html')

# --- 4. MuleSoft API Endpoints ---
@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    """Endpoint for the bookmarklet to sync Anypoint cookie."""
    data = request.json
    if data and 'cookie' in data:
        mule.set_session(data['cookie'])
        return jsonify({"status": "success", "message": "Session Synced"})
    return jsonify({"status": "error", "message": "No cookie found"}), 400

@app.route('/api/mule/orgs', methods=['GET'])
def get_mule_orgs():
    """Extract all Organizations from the synced profile."""
    orgs = mule.get_organizations()
    return jsonify(orgs)

@app.route('/api/mule/envs/<org_id>', methods=['GET'])
def get_mule_envs(org_id):
    """Extract Environments for a selected Organization."""
    envs = mule.get_environments(org_id)
    return jsonify(envs)

@app.route('/api/mule/apps', methods=['POST'])
def get_mule_apps():
    """Fetch apps for a specific Org and Env."""
    data = request.json
    apps = mule.get_runtime_apps(data['org_id'], data['env_id'])
    return jsonify(apps)

# --- 5. DevOps API Endpoints ---
@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    """Search Azure repos by prefix."""
    prefix = request.json.get('prefix', '')
    repos = devops.get_repositories(prefix)
    return jsonify({"repositories": repos})

@app.route('/api/extract-by-file', methods=['POST'])
def extract_by_file():
    """Filter Azure repos by a targeted list (CSV/TXT)."""
    repo_names = request.json.get('repos', [])
    all_repos = devops.get_repositories("") 
    matched = [r for r in all_repos if r['name'] in repo_names]
    return jsonify({"repositories": matched})

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    """Get all branch names for a repository."""
    branches = devops.get_branches(repo_name)
    return jsonify(branches)

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    """Get commit diff and file changes between two branches."""
    repo = request.args.get('repo')
    source = request.args.get('source', 'develop')
    target = request.args.get('target', 'main')
    details = devops.get_commit_details(repo, source, target)
    return jsonify(details)

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    """Create a single Pull Request in Azure."""
    data = request.json
    status, result = devops.create_pull_request(
        data['repo_id'], 
        data['from_branch'], 
        data['to_branch'],
        data.get('last_msg', 'Manual Trigger')
    )
    return jsonify({"status": status, "result": result})

@app.route('/api/bulk-create-pr', methods=['POST'])
def bulk_create_pr():
    """Execute multiple PR creations in parallel."""
    data = request.json
    operations = data.get('operations', [])
    
    def run_op(op):
        status, res = devops.create_pull_request(
            op['repo_id'], 
            op['from_branch'], 
            op['to_branch'],
            op.get('last_msg', 'Bulk Deployment')
        )
        return {"repo": op['repo_id'], "status": status, "details": res}

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(run_op, operations))

    return jsonify(results)

# --- Entry Point ---
if __name__ == '__main__':
    # Ensure you have run: pip install flask flask-cors requests
    app.run(debug=True, port=5000)