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
        Runs a single request using Newman.
        Captures the x-correlation-id from response headers or environment variables.
        """
        debug_mode = os.getenv("POSTMAN_DEBUG", "false").lower() == "true"
        # Phase 1: Create a temporary focused collection containing ONLY the target request
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
                log.error(f"Could not find request '{request_data['name']}' in collection.")
                return None

            # INJECT SCRIPT: If custom_script is provided, replace or add the 'test' event
            if custom_script:
                if 'event' not in target_item:
                    target_item['event'] = []
                # Remove existing test scripts
                target_item['event'] = [e for e in target_item['event'] if e.get('listen') != 'test']
                # Add the new one
                target_item['event'].append({
                    "listen": "test",
                    "script": {
                        "exec": custom_script.split('\n'),
                        "type": "text/javascript"
                    }
                })

            mini_col = {
                "info": {
                    "name": "Temp Execution",
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
                },
                "item": [target_item]
            }
            
            with open(temp_col_path, 'w') as f:
                json.dump(mini_col, f)

            # Phase 2: Execute via Newman
            report_path = os.path.join(tempfile.gettempdir(), f"report_{uuid.uuid4()}.json")
            
            cmd_parts = [
                "newman", "run", f'"{temp_col_path}"',
                "--reporters", "json",
                "--reporter-json-export", f'"{report_path}"'
            ]
            
            if environment_path and os.path.exists(environment_path):
                cmd_parts.extend(["-e", f'"{environment_path}"'])
            
            cmd_str = " ".join(cmd_parts)
            if debug_mode: log.info(f"Executing: {cmd_str}")
            
            result = subprocess.run(cmd_str, capture_output=True, text=True, timeout=45, shell=True)
            
            if debug_mode:
                if result.stdout: log.info(f"Newman STDOUT:\n{result.stdout}")
                if result.stderr: log.info(f"Newman STDERR:\n{result.stderr}")
            
            # Note: Newman often exits with code 1 if a request fails, but the report might still exist
            if not os.path.exists(report_path):
                log.error(f"Newman failed to generate report (Exit {result.returncode}).")
                if not debug_mode: # If not already printed, show stderr for troubleshooting
                    log.error(f"Newman Error Output: {result.stderr}")
                
            if os.path.exists(report_path):
                with open(report_path, 'r') as f:
                    report = json.load(f)
                
                if debug_mode:
                    log.info(f"Report structure: {list(report.keys())}")
                    if 'environment' in report:
                        log.info(f"Env values: {report['environment'].get('values', [])}")

                # Cleanup temp files
                try: os.remove(temp_col_path)
                except: pass
                try: os.remove(report_path)
                except: pass

                # Extraction Strategy A: Check Response Headers
                executions = report.get('run', {}).get('executions', [])
                for exe in executions:
                    headers = exe.get('response', {}).get('header', [])
                    
                    if debug_mode:
                        all_keys = [h.get('key') for h in headers]
                        log.info(f"Available Headers: {all_keys}")

                    for h in headers:
                        if h.get('key', '').lower() == 'x-correlation-id':
                            val = h.get('value')
                            if debug_mode: log.info(f"Found via Header: {val}")
                            return val
                
                # Extraction Strategy B: Check Environment Variables
                env_vars = report.get('environment', {}).get('values', [])
                for var in env_vars:
                    if var.get('key', '').lower() in ['correlationid', 'x-correlation-id']:
                        val = var.get('value')
                        if debug_mode: log.info(f"Found via Env Var: {val}")
                        return val
            else:
                log.error(f"Newman report file not found at {report_path}")
                
        except Exception as e:
            log.error(f"Postman execution exception: {e}")
            if os.path.exists(temp_col_path):
                try: os.remove(temp_col_path)
                except: pass

        return None
