from flask import Flask, render_template, request, jsonify
from devops_module import AzureDevOpsManager

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

@app.route('/api/branches/<repo_id>')
def get_branches(repo_id):
    branches = devops.get_branches(repo_id)
    return jsonify(branches)

@app.route('/api/create-pr', methods=['POST'])
def create_pr():
    data = request.json
    status, result = devops.create_pull_request(
        data['repo_id'], 
        data['from_branch'], 
        data['to_branch']
    )
    return jsonify({"status": status, "result": result})

@app.route('/api/repo-details', methods=['GET'])
def get_repo_details():
    # Use request.args for GET parameters (the ?repo= part)
    repo_name = request.args.get('repo')
    
    if not repo_name:
        return jsonify({"error": "Repository name is required"}), 400
    
    try:
        # Call the logic from your module
        details = devops.get_commit_details(repo_name)
        return jsonify(details)
    except Exception as e:
        print(f"Error fetching details for {repo_name}: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)