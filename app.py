from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from devops_module import AzureDevOpsManager
from mulesoft_module import MuleSoftManager, MuleSoftAuthError
from postman_module import PostmanManager
from boomi_module import BoomiManager
from dw_module import DataWeaveManager
from dw_lsp_manager import DataWeaveLSPManager
from concurrent.futures import ThreadPoolExecutor
import db_utils
import os
import sqlite3
import re
import json
import requests
import urllib3
from logger import log
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from json_logic import JSONLogicArchitect

db_utils.init_db()
app = Flask(__name__)
CORS(app) 

# Managers
devops = AzureDevOpsManager()
mule = MuleSoftManager()
postman = PostmanManager()
boomi = BoomiManager()
dw_engine = DataWeaveManager()
dw_lsp = DataWeaveLSPManager()
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
    return jsonify({
        "devops": devops.check_connection(),
        "mulesoft": mule.check_connection(),
        "boomi": boomi.check_connection()
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
    keys = ['azure_org', 'azure_project', 'azure_pat', 'mule_client_id', 'mule_client_secret', 'mule_bearer', 'mule_default_org', 'mule_default_env', 'boomi_account_id', 'boomi_username', 'boomi_api_key']
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
    boomi.refresh_configs()
    
    return jsonify({"status": "success", "message": "Settings updated and managers refreshed!"})

# --- Boomi APIs ---
@app.route('/boomi')
def boomi_index():
    return render_template('boomi/index.html')

@app.route('/boomi/discovery')
def boomi_discovery():
    return render_template('boomi/discovery.html')

@app.route('/api/boomi/components')
def boomi_api_components():
    ctype = request.args.get('type')
    components = boomi.get_components(ctype)
    return jsonify(components)

@app.route('/api/mule/orgs', methods=['GET'])
def get_mule_orgs():
    try:
        return jsonify(mule.get_organizations())
    except MuleSoftAuthError:
        return jsonify({"error": "Unauthorized"}), 401

@app.route('/api/mule/envs/<org_id>', methods=['GET'])
def get_mule_envs(org_id):
    import os, json
    if os.environ.get('MOCK_MONITORING', 'false').lower() == 'true':
        with open('data/anypoint_envs.json', 'r') as f:
            return jsonify(json.load(f))
    try:
        return jsonify(mule.get_environments(org_id))
    except MuleSoftAuthError:
        return jsonify({"error": "Unauthorized"}), 401

@app.route('/boomi/dependency-tree')
def boomi_dependency_tree():
    return render_template('boomi/dependency_tree.html')

@app.route('/api/boomi/package-dependencies')
def boomi_api_package_dependencies():
    name = request.args.get('name')
    version = request.args.get('version')
    log.debug(f"API Trigger: Dependency Tree for '{name}' (v:{version})")
    if not name: return jsonify({"error": "Name required"}), 400
    
    pkg = boomi.get_package_by_name(name, version)
    if not pkg: 
        log.warning(f"Dependency Tree Search: No Package found for '{name}'")
        return jsonify({"error": "Package not found"}), 404
    
    # Defensive retrieval of component name for root manifest context
    root_name = pkg.get('componentName') or name
    manifest = boomi.get_package_manifest(pkg['packageId'], root_name=root_name)
    if not manifest: 
        log.warning(f"Dependency Tree Search: No Manifest found for package {pkg['packageId']}")
        return jsonify({"error": "Manifest not found"}), 404
    
    return jsonify({
        "package": pkg,
        "included": manifest.get('includedComponent', [])
    })

# --- DataWeave Playround ---
@app.route('/mulesoft/dw-playground')
def dw_playground():
    return render_template('mulesoft/dw_playground.html')

@app.route('/api/dw/evaluate', methods=['POST'])
def dw_evaluate_api():
    data = request.json
    inputs = data.get('inputs', {})   # Map of {name: {content, type}}
    scripts = data.get('scripts', {}) # Map of {filename: content}
    
    if not inputs and not scripts:
        return jsonify({"success": False, "error": "No data provided"})
        
    result = dw_engine.evaluate(inputs, scripts)
    return jsonify(result)

@app.route('/api/dw/autocomplete', methods=['POST'])
def dw_autocomplete_api():
    data = request.json
    context_code = data.get('text', '')
    # Monaco lines are 1-indexed, LSP is 0-indexed
    line = data.get('line', 1) - 1
    character = data.get('column', 1) - 1
    
    suggestions = dw_lsp.get_lsp_completions(context_code, line, character)
    
    # If LSP returns empty array, fallback to static snippets
    if not suggestions:
        suggestions = dw_lsp.static_snippets
        
    return jsonify({"success": True, "suggestions": suggestions})

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

# --- Logs Dashboard ---
@app.route('/mulesoft/logs')
def logs_dashboard():
    default_org = db_utils.get_setting('mule_default_org', '')
    default_env = db_utils.get_setting('mule_default_env', '')
    return render_template('mulesoft/logs_dashboard.html', default_org=default_org, default_env=default_env)

@app.route('/logs/api/apps')
def logs_api_apps():
    import os, json
    if os.environ.get('MOCK_MONITORING', 'false').lower() == 'true':
        with open('data/anypoint_apps.json', 'r') as f:
            return jsonify(json.load(f))
            
    org_id = request.args.get('org_id')
    env_id = request.args.get('env_id')
    if not org_id or not env_id:
        return jsonify([])
    apps = mule.get_runtime_apps(org_id, env_id, extract_details=False)
    return jsonify(apps)

@app.route('/logs/api/auth/test', methods=['POST'])
def logs_api_auth_test():
    import os, json
    if os.environ.get('MOCK_MONITORING', 'false').lower() == 'true':
        with open('data/anypoint_auth_test.json', 'r') as f:
            return jsonify(json.load(f))
            
    is_connected = mule.check_connection()
    if is_connected:
        try:
            orgs = mule.get_organizations()
            return jsonify({"status": "success", "orgs": orgs})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "error", "message": "Authentication failed"}), 401

@app.route('/logs/api/events')
def logs_api_events():
    org_id = request.args.get('org_id')
    env_id = request.args.get('env_id')
    app_id = request.args.get('app_id')
    log_level = request.args.get('log_level', 'ALL Level')
    start_time = request.args.get('startTime')
    end_time = request.args.get('endTime')
    
    if not all([org_id, env_id, start_time, end_time]):
        return jsonify({"error": "Missing required parameters"}), 400
        
    try:
        start_time = int(start_time)
        end_time = int(end_time)
    except ValueError:
        return jsonify({"error": "Invalid time format. Must be epoch milliseconds"}), 400

    # Fetch logs - capped at 500 as per user requirement
    limit = 500
    res = mule.fetch_logs(org_id, env_id, app_id, start_time, end_time, log_level=log_level, limit=limit, order="DESC")
    all_logs = res.get("logs", [])
    aggregations = res.get("aggregations", [])
    is_capped = len(all_logs) >= limit

    # Group by correlationId
    groups = {}
    severity_order = {"ERROR": 4, "WARN": 3, "INFO": 2, "DEBUG": 1}
    
    import uuid
    
    # Pre-parse and sort logs by timestamp
    for line in all_logs:
        cid = line.get('correlationId')
        # If no correlation ID exists, generate a unique one for this log so it doesn't merge with other unrelated logs
        if not cid or str(cid).strip().lower() == 'unknown':
            cid = f"no-corr-id-{uuid.uuid4().hex[:8]}"
            line['correlationId'] = cid
            
        if cid not in groups:
            groups[cid] = {
                "correlationId": cid,
                "firstSeen": float('inf'),
                "lastSeen": 0,
                "duration": 0,
                "logCount": 0,
                "highestSeverity": "DEBUG",
                "hasError": False,
                "applicationName": line.get('applicationName', 'Unknown App'),
                "workerId": line.get('workerId', 'Unknown Worker'),
                "lines": []
            }
        
        g = groups[cid]
        ts = line.get('timestamp', 0)
        
        if ts < g["firstSeen"]: g["firstSeen"] = ts
        if ts > g["lastSeen"]: g["lastSeen"] = ts
        
        g["logCount"] += 1
        
        level = (line.get('logLevel') or "DEBUG").upper()
        if severity_order.get(level, 0) > severity_order.get(g["highestSeverity"], 0):
            g["highestSeverity"] = level
        if level == "ERROR":
            g["hasError"] = True
            
        g["lines"].append(line)
        
    for g in groups.values():
        g["duration"] = g["lastSeen"] - g["firstSeen"]
        if g["firstSeen"] == float('inf'):
            g["firstSeen"] = 0
        g["lines"].sort(key=lambda x: x.get('timestamp', 0)) # ASC for detail view
        
    # Sort groups by firstSeen DESC
    sorted_groups = sorted(groups.values(), key=lambda x: x["firstSeen"], reverse=True)
    
    return jsonify({
        "events": sorted_groups,
        "aggregations": aggregations,
        "is_capped": is_capped
    })

@app.route('/logs/api/events/<corr_id>')
def logs_api_event_detail(corr_id):
    # Normally this would fetch explicitly, but since the events route returns the lines,
    # we can just have the frontend use the returned lines or we can build this if needed.
    # To satisfy the spec "GET /logs/api/events/<corrId>", we can query it directly
    org_id = request.args.get('org_id')
    env_id = request.args.get('env_id')
    app_id = request.args.get('app_id')
    start_time = request.args.get('startTime')
    end_time = request.args.get('endTime')
    
    if not all([org_id, env_id, start_time, end_time]):
        return jsonify({"error": "Missing required parameters"}), 400
        
    try:
        start_time = int(start_time)
        end_time = int(end_time)
    except ValueError:
        return jsonify({"error": "Invalid time format"}), 400
        
    query = f"\"{corr_id}\""
    
    res = mule.fetch_logs(org_id, env_id, app_id, start_time, end_time, query=query, limit=1000, order="ASC")
    return jsonify(res.get("logs", []))

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
        
    elif mode == 'xml':
        # Direct XML comparison
        xml_a = data.get('response_a_xml', '')
        xml_b = data.get('response_b_xml', '')
        
        import xml.etree.ElementTree as ET
        
        def parse_xml_root(xml_string):
            if not xml_string.strip(): return None
            try:
                return ET.fromstring(xml_string)
            except Exception as e:
                return {"error": f"Invalid XML: {str(e)}"}
                
        root_a = parse_xml_root(xml_a)
        if isinstance(root_a, dict) and "error" in root_a: return jsonify(root_a), 400
        root_b = parse_xml_root(xml_b)
        if isinstance(root_b, dict) and "error" in root_b: return jsonify(root_b), 400

        comparator = PostmanComparator(exempted_fields=exempted)
        res = comparator.compare(root_a, root_b, format="xml")
        res.update({
            "method": "MANUAL",
            "curl": "N/A",
            "response_a_raw": xml_a,
            "response_b_raw": xml_b,
            "collection_name": data.get('collection_name', 'Manual XML Input')
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
    
    try:
        iterations = int(data.get('iterations', 1))
    except (ValueError, TypeError):
        iterations = 1
        
    try:
        delay_ms = int(data.get('delay', 0))
    except (ValueError, TypeError):
        delay_ms = 0

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
        total_count = len(items) * iterations
        yield json.dumps({"type": "run_start", "total": total_count}) + "\n"
        
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
                    "response": res.get('response', ''),
                    "headers": res.get('headers', {}),
                    "curl": res.get('curl', ''),
                    "url": res.get('url', '')
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