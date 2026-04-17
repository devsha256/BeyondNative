from flask import Flask, render_template, request, jsonify
from devops_module import AzureDevOpsManager
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
devops = AzureDevOpsManager()

@app.route('/')
def index():
    return render_template('devops/discovery.html')

@app.route('/devops/bulk-pr')
def bulk_pr_view():
    return render_template('devops/bulk_pr.html')

@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    repos = devops.get_repositories(prefix)
    return jsonify({"repositories": repos})

@app.route('/api/extract-by-file', methods=['POST'])
def extract_by_file():
    # Expects a JSON list of repo names from the frontend
    repo_names = request.json.get('repos', [])
    all_repos = devops.get_repositories("") # Get all to match URLs and project names
    
    # Filter only the repos provided in the file
    matched = [r for r in all_repos if r['name'] in repo_names]
    return jsonify({"repositories": matched})

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
    status, result = devops.create_pull_request(
        data['repo_id'], 
        data['from_branch'], 
        data['to_branch'],
        data.get('last_msg', 'Manual Trigger')
    )
    return jsonify({"status": status, "result": result})

@app.route('/api/bulk-create-pr', methods=['POST'])
def bulk_create_pr():
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

if __name__ == '__main__':
    app.run(debug=True)