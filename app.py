from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager, MuleSoftAuthError
from postman_module import PostmanManager
from concurrent.futures import ThreadPoolExecutor
import db_utils
import os
import sqlite3
import re
import json
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from json_logic import JSONLogicArchitect

db_utils.init_db()
app = Flask(__name__)
CORS(app) 

# Managers
devops = AzureDevOpsManager()
mule = MuleSoftManager()
postman = PostmanManager()
jq_architect = JSONLogicArchitect()

# --- JQ Logic APIs ---
@app.route('/api/jq/filter', methods=['POST'])
def jq_filter_api():
    data = request.json
    raw_json = data.get('data')
    filter_str = data.get('filter', '.')
    
    if not raw_json:
        return jsonify({"error": "Raw data is required for filtering"}), 400
        
    result = jq_architect.search_json(raw_json, filter_str)
    return jsonify(result)

# --- Navigation ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/health-check')
def health_check_api():
    # Execute checks (could be in parallel but even sequential here is better than blocking index)
    return jsonify({
        "devops": devops.check_connection(),
        "mulesoft": mule.check_connection()
    })

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
    default_org = db_utils.get_setting('mule_default_org', '')
    default_env = db_utils.get_setting('mule_default_env', '')
    return render_template('mulesoft/runtime_control.html', default_org=default_org, default_env=default_env)

@app.route('/mulesoft/version-comparator')
def version_comparator():
    default_org = db_utils.get_setting('mule_default_org', '')
    default_env = db_utils.get_setting('mule_default_env', '')
    return render_template('mulesoft/version_comparator.html', default_org=default_org, default_env=default_env)

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
        results = list(executor.map(devops.get_repository, repo_names))
        
    for r in results:
        if r:
            matched.append(r)
            
    # Fallback: if parallel requests failed (e.g. 404 by name, or 429 rate limit)
    if not matched and repo_names:
        all_repos = devops.get_repositories("")
        matched = [r for r in all_repos if r['name'] in repo_names]
        
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
        data['repo_id'], data['from_branch'], data['to_branch'], data.get('last_msg'),
        auto_complete=data.get('auto_complete', False)
    )
    return jsonify({"status": status, "result": result})

@app.route('/api/bulk-create-pr', methods=['POST'])
def bulk_create_pr():
    data = request.json
    operations = data.get('operations', [])
    def run_op(op):
        status, res = devops.create_pull_request(
            op['repo_id'], op['from_branch'], op['to_branch'], op.get('last_msg'),
            auto_complete=op.get('auto_complete', False)
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
    keys = ['azure_org', 'azure_project', 'azure_pat', 'mule_client_id', 'mule_client_secret', 'mule_bearer', 'mule_default_org', 'mule_default_env']
    setting_vals = {k: db_utils.get_setting(k) for k in keys}
    return render_template('settings.html', settings=setting_vals)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    if not data: return jsonify({"error": "No data"}), 400
    for k, v in data.items():
        db_utils.set_setting(k, v)
    
    # Force managers to reload their configs from DB
    devops.refresh_configs()
    mule.refresh_configs()
    
    return jsonify({"status": "success", "message": "Settings updated and managers refreshed!"})

@app.route('/api/mule/orgs', methods=['GET'])
def get_mule_orgs():
    try:
        return jsonify(mule.get_organizations())
    except MuleSoftAuthError:
        return jsonify({"error": "Unauthorized"}), 401

@app.route('/api/mule/envs/<org_id>', methods=['GET'])
def get_mule_envs(org_id):
    try:
        return jsonify(mule.get_environments(org_id))
    except MuleSoftAuthError:
        return jsonify({"error": "Unauthorized"}), 401

@app.route('/api/mule/apps', methods=['POST'])
def fetch_mule_apps():
    data = request.json
    extract_details = data.get('extract_details', False)
    apps = mule.get_runtime_apps(data.get('org_id'), data.get('env_id'), extract_details=extract_details)
    return jsonify(apps)

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

# ==========================================
# Postman Suite
# ==========================================

@app.route('/postman')
def postman_home():
    return render_template('postman/index.html')

@app.route('/postman/runner')
def postman_runner():
    return render_template('postman/runner.html')

from postman_compare_module import PostmanComparator, validate_urls, compare_responses as compare_raw_responses

# Help resolve host replacement and cURL parsing
def parse_curl(curl_command):
    # Clean the curl command
    curl_command = curl_command.replace('\\\n', ' ').replace('\n', ' ').strip()
    
    components = {
        'url': '',
        'method': 'GET',
        'headers': {},
        'body': None
    }
    
    # 1. Extract URL - Look for http(s) strictly first, then any quoted string that looks like a URL
    url_match = re.search(r"'(https?://[^']+)'|\"(https?://[^\"]+)\"|(https?://[^\s']+)", curl_command)
    if not url_match:
        # Fallback for URLs without http prefix
        url_match = re.search(r"curl\s+(?:--location\s+)?(?:--request\s+\w+\s+)?['\"]?([^'\s\"]+)['\"]?", curl_command)
        
    if url_match:
        components['url'] = next((g for g in url_match.groups() if g), "")
        
    # 2. Extract Method
    method_match = re.search(r"(?:--request|-X)\s+([A-Z]+)", curl_command)
    if method_match:
        components['method'] = method_match.group(1)
    elif "--data" in curl_command or "--data-raw" in curl_command or "-d " in curl_command:
        components['method'] = 'POST'
        
    # 3. Extract Headers
    header_matches = re.finditer(r"(?:--header|-H)\s+['\"]([^:]+):\s*([^'\"]+)['\"]", curl_command)
    for match in header_matches:
        components['headers'][match.group(1).strip()] = match.group(2).strip()
        
    # 4. Extract Body
    body_match = re.search(r"(?:--data(?:-raw)?|-d)\s+'([\s\S]*?)'", curl_command)
    if body_match:
        components['body'] = body_match.group(1).replace("\\'", "'").replace("\\\\", "\\")
        
    return components

# Compare UI
@app.route('/postman/compare')
def postman_compare_page():
    import db_utils
    settings = {
        'source_host': db_utils.get_setting('postman_source_host') or 'https://boomi-api.com',
        'target_host': db_utils.get_setting('postman_target_host') or 'https://mule-api.com',
        'exemptions': db_utils.get_setting('postman_exemptions') or '["timestamp", "uuid", "transactionId"]'
    }
    return render_template('postman/compare.html', settings=settings)

# Compare API - Execute
@app.route('/api/postman/compare/execute', methods=['POST'])
def postman_compare_execute():
    data = request.json
    mode = data.get('mode', 'json') # 'json', 'curl', 'collection'
    exempted = data.get('exempted_fields', [])
    source_host = data.get('source_host') # e.g. http://boomi-api.com
    target_host = data.get('target_host') # e.g. http://mule-api.com
    
    results = []
    
    if mode == 'json':
        # Direct JSON comparison
        resp_a = data.get('response_a', {})
        resp_b = data.get('response_b', {})
        comparator = PostmanComparator(exempted_fields=exempted)
        res = comparator.compare(resp_a, resp_b)
        res.update({
            "method": "MANUAL",
            "curl": "N/A",
            "response_a_raw": resp_a,
            "response_b_raw": resp_b,
            "collection_name": data.get('collection_name', 'Manual Input')
        })
        return jsonify(res)
        
    elif mode == 'curl':
        curl_a = data.get('curl_a')
        curl_b = data.get('curl_b')
        
        if not curl_a or not curl_b:
            return jsonify({"error": "Both cURLs are required"}), 400
            
        comp_a = parse_curl(curl_a)
        comp_b = parse_curl(curl_b)
        
        # Validation
        valid, msg = validate_urls(comp_a['url'], comp_b['url'])
        if not valid:
            return jsonify({"error": msg}), 400
            
        # Execute both
        try:
            print(f"[DEBUG] Executing A: {comp_a['method']} {comp_a['url']}")
            res_a = requests.request(comp_a['method'], comp_a['url'], headers=comp_a['headers'], data=comp_a['body'], timeout=15, verify=False)
            res_b = requests.request(comp_b['method'], comp_b['url'], headers=comp_b['headers'], data=comp_b['body'], timeout=15, verify=False)
            
            try:
                data_a = res_a.json()
            except:
                data_a = res_a.text
                
            try:
                data_b = res_b.json()
            except:
                data_b = res_b.text
            
            comparator = PostmanComparator(exempted_fields=exempted)
            comparison_res = comparator.compare(data_a, data_b)
            
            comparison_res.update({
                "method": comp_a['method'],
                "curl": curl_a,
                "response_a_raw": data_a,
                "response_b_raw": data_b,
                "collection_name": data.get('collection_name', 'cURL Import')
            })
            return jsonify(comparison_res)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return jsonify({"error": f"Execution failed: {str(e)}"}), 500
            
    elif mode == 'collection':
        request_obj = data.get('request_details')
        if not request_obj:
            return jsonify({"error": "Request details are missing"}), 400
            
        method = request_obj.get('method', 'GET')
        url_data = request_obj.get('url', '')
        
        raw_url = ""
        if isinstance(url_data, dict):
            raw_url = url_data.get('raw', '')
        else:
            raw_url = str(url_data)
            
        # Extract Path + Query only
        # We assume the user provides source_host/target_host as the base
        from urllib.parse import urlparse
        parsed = urlparse(raw_url)
        path_query = parsed.path
        if parsed.query: path_query += f"?{parsed.query}"
        
        # Ensure path starts with /
        if not path_query.startswith('/'): path_query = '/' + path_query
        
        url_a = source_host.rstrip('/') + path_query
        url_b = target_host.rstrip('/') + path_query
        
        # Prepare Headers
        headers = {}
        for h in request_obj.get('header', []):
            if not h.get('disabled', False):
                headers[h.get('key')] = h.get('value')
        
        # Prepare Body
        body = None
        if 'body' in request_obj and request_obj['body'].get('mode') == 'raw':
            body = request_obj['body'].get('raw')
            
        # Execute
        try:
            print(f"[DEBUG] Collection Mode Execution - Path: {path_query}")
            print(f"Executing A: {url_a}")
            print(f"Executing B: {url_b}")
            
            res_a = requests.request(method, url_a, headers=headers, data=body, timeout=15, verify=False)
            res_b = requests.request(method, url_b, headers=headers, data=body, timeout=15, verify=False)
            
            def safe_parse(r):
                try: return r.json()
                except: return r.text
                
            data_a = safe_parse(res_a)
            data_b = safe_parse(res_b)
            
            comparator = PostmanComparator(exempted_fields=exempted)
            comparison_res = comparator.compare(data_a, data_b)
            
            comparison_res.update({
                "method": method,
                "curl": f"Source: {url_a} \nTarget: {url_b}",
                "response_a_raw": data_a,
                "response_b_raw": data_b,
                "collection_name": data.get('collection_name', 'Collection Import')
            })

            # Persistent Session Recording
            session_id = data.get('session_id')
            if session_id:
                import db_utils
                db_utils.record_comparison_result(
                    session_id,
                    comparison_res['collection_name'],
                    method,
                    comparison_res['status'],
                    comparison_res['match_percent'],
                    comparison_res['stats'],
                    comparison_res['curl'],
                    data_a, data_b
                )

            return jsonify(comparison_res)
        except Exception as e:
            return jsonify({"error": f"Collection Execution Failed: {str(e)}"}), 500
    
    return jsonify({"error": "Unsupported mode"}), 400

@app.route('/api/postman/compare/session/start', methods=['POST'])
def start_session():
    import uuid
    import db_utils
    data = request.json
    session_id = str(uuid.uuid4())
    collection_name = data.get('collection_name', 'Untitled Session')
    db_utils.start_comparison_session(session_id, collection_name)
    return jsonify({"session_id": session_id})

@app.route('/api/postman/compare/session/export/<session_id>')
def export_session(session_id):
    import db_utils
    import json
    import csv
    from io import StringIO
    from flask import Response
    
    results = db_utils.get_session_results(session_id)
    si = StringIO()
    cw = csv.writer(si)
    
    cw.writerow(["Timestamp", "Collection/Request", "Method", "Status", "Match %", "Mismatched", "Exempted", "Only A", "Only B", "Details", "Response A", "Response B"])
    
    for r in results:
        stats = json.loads(r['stats_json'] or '{}')
        cw.writerow([
            r['timestamp'],
            r['request_name'],
            r['method'],
            r['status'],
            f"{r['match_percent']}%",
            stats.get('totalMismatches', 0),
            stats.get('totalExempted', 0),
            stats.get('totalOnlyA', 0),
            stats.get('totalOnlyB', 0),
            r['curl_details'],
            r['resp_a_raw'],
            r['resp_b_raw']
        ])
    
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=session_audit_{session_id}.csv"}
    )

# Compare API - Storage
@app.route('/api/postman/compare/save-artifact', methods=['POST'])
def postman_compare_save_artifact():
    data = request.json
    type = data.get('type') # 'curl' or 'collection'
    name = data.get('name')
    content = data.get('content')
    
    if not name or not content:
        return jsonify({"error": "Name and content required"}), 400
        
    folder = "curls" if type == "curl" else "collections"
    path = os.path.join("post_work_dir", "compares", folder, name)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content if isinstance(content, str) else json.dumps(content, indent=2))
        
    return jsonify({"status": "success", "path": path})

@app.route('/postman/log-report')
def postman_log_report():
    return render_template('postman/log_report.html')

# --- Postman APIs ---

@app.route('/api/postman/scan', methods=['POST'])
def postman_scan():
    data = request.json
    folder = data.get('folder')
    if not folder: return jsonify({"error": "Folder path is required"}), 400
    
    collections = postman.scan_folder_for_collections(folder)
    all_requests = []
    for col in collections:
        all_requests.extend(postman.extract_requests_from_collection(col['path']))
        
    return jsonify({
        "collections": collections,
        "requests": all_requests
    })

@app.route('/api/postman/sync', methods=['POST'])
def postman_sync():
    data = request.json
    filename = data.get('filename')
    content = data.get('content')
    type = data.get('type') # 'collection' or 'environment'
    
    if not filename or not content:
        return jsonify({"error": "Missing filename or content"}), 400
    
    subfolder = "collections" if type == "collection" else "environments"
    path = postman.save_file(filename, content, subfolder)
    
    return jsonify({"status": "success", "path": path})

@app.route('/api/postman/execute-stream', methods=['POST'])
def postman_execute_stream():
    import time
    data = request.json
    collection = data.get('collection')
    environment = data.get('environment', {})
    iterations = int(data.get('iterations', 1))
    delay_ms = int(data.get('delay', 0))

    if not collection: return jsonify({"error": "No collection provided"}), 400
    
    # 1. Merge Variables
    base_vars = {}
    # Collection variables
    for v in collection.get('variable', []):
        base_vars[v.get('key')] = v.get('value')
    # Environment variables override
    if environment and isinstance(environment, dict):
        for v in environment.get('values', []):
            if v.get('enabled', True):
                base_vars[v.get('key')] = v.get('value')
            
    # 2. Extract linear list of requests
    items = []
    def recurse(obj_items):
        for i in obj_items:
            if 'request' in i: items.append(i)
            if 'item' in i: recurse(i['item'])
    recurse(collection.get('item', []))

    def generate():
        for it in range(iterations):
            for item in items:
                # Signal request start
                yield json.dumps({"type": "request_start", "item_name": item.get('name')}) + "\n"
                
                # Execute
                start_time = time.time()
                res = postman.execute_collection_item(item, base_vars)
                end_time = time.time()
                
                duration = int((end_time - start_time) * 1000)
                
                # Signal completion
                status_text = "OK" if res.get('status_code', 0) < 400 else "ERROR"
                yield json.dumps({
                    "type": "request_complete",
                    "item_name": item.get('name'),
                    "method": res.get('method', '???'),
                    "status_code": res.get('status_code', 500),
                    "status_text": status_text,
                    "duration": duration,
                    "response": res.get('response', '')[:500] 
                }) + "\n"
                
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                    
        yield json.dumps({"type": "run_complete"}) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

@app.route('/api/postman/execute-single', methods=['POST'])
def postman_execute_single():
    data = request.json
    req = data.get('request')
    env = data.get('environment')
    script = data.get('script') # Optional user edited script
    
    # Run the request via PostmanManager
    correlation_id = postman.run_request(req, env, script)
    return jsonify({"correlation_id": correlation_id})

@app.route('/api/postman/generate-logs', methods=['POST'])
def postman_generate_logs():
    data = request.json
    ids = data.get('correlation_ids', [])
    extractor_path = data.get('extractor_path')
    env_path = data.get('environment')
    
    if not ids: return jsonify({"error": "No IDs provided"}), 400
    if not extractor_path: return jsonify({"error": "No Log Extractor collection provided"}), 400

    report_result = postman.aggregate_logs(ids, extractor_path, env_path)
    
    if "error" in report_result:
        return jsonify(report_result), 500
        
    return jsonify(report_result)
    
@app.route('/api/postman/history/save', methods=['POST'])
def save_report_history():
    data = request.json
    title = data.get('title', 'Untitled Report')
    report_data = data.get('data', [])
    
    if not report_data:
        return jsonify({"error": "No report data to save"}), 400
        
    with db_utils.get_db() as conn:
        conn.execute("INSERT INTO log_report_history (title, data) VALUES (?, ?)", (title, json.dumps(report_data)))
        conn.commit()
    return jsonify({"status": "success", "message": "Report saved to history!"})

@app.route('/api/postman/history', methods=['GET'])
def get_report_history_list():
    with db_utils.get_db() as conn:
        rows = conn.execute("SELECT id, title, timestamp FROM log_report_history ORDER BY timestamp DESC").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/postman/history/<int:report_id>', methods=['GET'])
def get_report_history_detail(report_id):
    with db_utils.get_db() as conn:
        row = conn.execute("SELECT * FROM log_report_history WHERE id = ?", (report_id,)).fetchone()
        if row:
            data = dict(row)
            data['data'] = json.loads(data['data'])
            return jsonify(data)
    return jsonify({"error": "Report not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5001, threaded=True)