import os
import json
import subprocess
import tempfile
import uuid
from logger import log

class PostmanManager:
    def __init__(self):
        self.work_dir = os.path.join(os.getcwd(), "post_work_dir")
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

    def save_file(self, filename, content, subfolder=""):
        """Saves a file to the post_work_dir."""
        target_dir = os.path.join(self.work_dir, subfolder)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        path = os.path.join(target_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f, indent=4)
        return path

    def scan_folder_for_collections(self, root_dir):
        """Recursively finds all .postman_collection.json files in a directory."""
        collections = []
        if not os.path.exists(root_dir):
            return []
        
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.postman_collection.json'):
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            collections.append({
                                "name": data.get('info', {}).get('name', file),
                                "path": full_path,
                                "relative_path": os.path.relpath(full_path, root_dir)
                            })
                    except Exception as e:
                        log.error(f"Error parsing collection {file}: {e}")
        return collections

    def extract_requests_from_collection(self, collection_path):
        """Extracts all request items from a Postman collection JSON."""
        requests = []
        try:
            with open(collection_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            def recurse_items(items, parent_folder=""):
                for item in items:
                    name = item.get('name', 'Unnamed Item')
                    full_name = f"{parent_folder} > {name}" if parent_folder else name
                    
                    if 'request' in item:
                        req_data = item.get('request', {})
                        url = req_data.get('url', '')
                        if isinstance(url, dict):
                            url = url.get('raw', '')
                        
                        # Extract script if available
                        script = ""
                        events = item.get('event', [])
                        for event in events:
                            if event.get('listen') == 'test':
                                script = "\n".join(event.get('script', {}).get('exec', []))
                        
                        requests.append({
                            "id": str(uuid.uuid4()),
                            "name": name,
                            "full_name": full_name,
                            "method": req_data.get('method', 'GET'),
                            "url": url,
                            "collection_path": collection_path,
                            "script": script or "// Default script will be injected if empty\n"
                        })
                    
                    if 'item' in item:
                        recurse_items(item['item'], full_name)
            
            recurse_items(data.get('item', []))
        except Exception as e:
            log.error(f"Failed to extract requests from {collection_path}: {e}")
        
        return requests

    def run_request(self, request_data, environment_path=None, custom_script=None):
        """
        Runs a single request and extracts x-correlation-id.
        Features triple-redundancy: Console Log Grep, JSON Header Scan, and Env Var Scan.
        """
        debug_mode = os.getenv("POSTMAN_DEBUG", "false").lower() == "true"
        temp_col_path = os.path.join(tempfile.gettempdir(), f"temp_req_{uuid.uuid4()}.json")
        
        try:
            with open(request_data['collection_path'], 'r', encoding='utf-8') as f:
                original = json.load(f)
            
            def find_item_by_name(items, target_name):
                for item in items:
                    if item.get('name') == target_name and 'request' in item:
                        return item
                    if 'item' in item:
                        res = find_item_by_name(item['item'], target_name)
                        if res: return res
                return None

            target_item = find_item_by_name(original.get('item', []), request_data['name'])
            if not target_item:
                return None

            # AUTO-INJECTION: We ALWAYS inject a console.log script for ultimate reliability
            # This works even if JSON reporters fail or omit data
            extraction_script = 'console.log("CID_CAPTURE:" + pm.response.headers.get("x-correlation-id"));'
            if custom_script:
                extraction_script += "\n" + custom_script

            if 'event' not in target_item: target_item['event'] = []
            target_item['event'] = [e for e in target_item['event'] if e.get('listen') != 'test']
            target_item['event'].append({
                "listen": "test",
                "script": { "exec": extraction_script.split('\n'), "type": "text/javascript" }
            })

            mini_col = {
                "info": { "name": "AutoExtract", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json" },
                "item": [target_item]
            }
            with open(temp_col_path, 'w') as f: json.dump(mini_col, f)

            report_path = os.path.join(tempfile.gettempdir(), f"report_{uuid.uuid4()}.json")
            cmd_parts = [
                "newman", "run", f'"{temp_col_path}"',
                "--reporters", "json", "--reporter-json-export", f'"{report_path}"'
            ]
            if environment_path and os.path.exists(environment_path):
                cmd_parts.extend(["-e", f'"{environment_path}"'])
            
            cmd_str = " ".join(cmd_parts)
            result = subprocess.run(cmd_str, capture_output=True, text=True, timeout=45, shell=True)

            # DIAGNOSTIC: Log full failure details if report doesn't exist
            if not os.path.exists(report_path):
                log.error(f"Newman execution failed (Exit {result.returncode})")
                log.error(f"CMD attempted: {cmd_str}")
                if result.stderr: log.error(f"Newman STDERR: {result.stderr.strip()}")
                if result.stdout: log.error(f"Newman STDOUT: {result.stdout.strip()[:500]}")
                
                # OPTIONAL FALLBACK: Try npx if the system can't find 'newman'
                if "not found" in result.stderr.lower() or "not recognized" in result.stderr.lower():
                    log.info("Attempting fallback via npx...")
                    npx_cmd = "npx " + cmd_str
                    result = subprocess.run(npx_cmd, capture_output=True, text=True, timeout=60, shell=True)
                    if os.path.exists(report_path):
                        log.info("npx fallback successful!")

            # STRATEGY 1: Grep Stdout for the captured string (Most reliable)
            if result.stdout and "CID_CAPTURE:" in result.stdout:
                line = [l for l in result.stdout.split('\n') if "CID_CAPTURE:" in l][0]
                cid = line.split("CID_CAPTURE:")[1].strip()
                if cid and cid != "undefined" and cid != "null":
                    if debug_mode: log.info(f"Captured via Stdout Grep: {cid}")
                    return cid

            # STRATEGY 2 & 3: Fallback to JSON Report
            if os.path.exists(report_path):
                with open(report_path, 'r') as f:
                    report = json.load(f)
                
                # Check Headers
                executions = report.get('run', {}).get('executions', [])
                for exe in executions:
                    headers = exe.get('response', {}).get('header', [])
                    for h in headers:
                        if h.get('key', '').lower() == 'x-correlation-id':
                            val = h.get('value')
                            if val: return val
                
                # Check Environment
                env_vars = report.get('environment', {}).get('values', [])
                for var in env_vars:
                    if var.get('key', '').lower() in ['correlationid', 'x-correlation-id']:
                        val = var.get('value')
                        if val: return val
            
            if debug_mode: log.error(f"Extraction failed. Newman Output: {result.stdout[:200]}")
                
        except Exception as e:
            log.error(f"Postman execution exception: {e}")
        finally:
            if os.path.exists(temp_col_path): os.remove(temp_col_path)
            # report_path cleanup handled above or left for OS temp cleanup

        return None
