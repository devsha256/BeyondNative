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

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    branches = devops.get_branches(repo_name)
    return jsonify(branches)

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    repo_name = request.args.get('repo')
    if not repo_name:
        return jsonify({"error": "No repository name provided"}), 400
    details = devops.get_commit_details(repo_name)
    return jsonify(details)

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    data = request.json
    status, result = devops.create_pull_request(
        data['repo_id'], 
        data['from_branch'], 
        data['to_branch']
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
            op['to_branch']
        )
        return {"repo": op['repo_id'], "status": status, "details": res}

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(run_op, operations))

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)