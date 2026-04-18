from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager

app = Flask(__name__)
# CRITICAL: CORS must be enabled to allow the Anypoint tab to talk to localhost
CORS(app) 

devops = AzureDevOpsManager()
mule = MuleSoftManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/mulesoft/runtime-control')
def runtime_control():
    return render_template('mulesoft/runtime_control.html')

@app.route('/api/mule/set-session', methods=['POST'])
def set_mule_session():
    data = request.json
    if data and 'cookie' in data:
        mule.set_session(data['cookie'])
        print(">>> MuleSoft Session Synchronized Successfully")
        return jsonify({"status": "success", "message": "Session Synced"})
    return jsonify({"status": "error", "message": "No cookie data received"}), 400

@app.route('/api/mule/apps', methods=['POST'])
def get_mule_apps():
    data = request.json
    apps = mule.get_runtime_apps(data['org_id'], data['env_id'])
    return jsonify(apps)

if __name__ == '__main__':
    app.run(debug=True)