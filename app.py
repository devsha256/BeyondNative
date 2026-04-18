from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager

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

# --- APIs ---
@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    data = request.json
    if data and 'cookie' in data:
        mule.set_session(data['cookie'])
    return jsonify({"status": "Session Synced"})

@app.route('/api/extract-repos', methods=['POST'])
def extract_repos():
    prefix = request.json.get('prefix', '')
    repos = devops.get_repositories(prefix)
    return jsonify({"repositories": repos})

@app.route('/api/branches/<repo_name>')
def get_branches(repo_name):
    branches = devops.get_branches(repo_name)
    return jsonify(branches)

if __name__ == '__main__':
    app.run(debug=True)