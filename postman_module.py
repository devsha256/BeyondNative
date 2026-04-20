import requests
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

    def _resolve_variables(self, text, variables):
        """Resolves {{variable}} placeholders using the provided dictionary."""
        if not isinstance(text, str): return text
        import re
        pattern = re.compile(r"\{\{([^\{\}]+)\}\}")
        
        def replace(match):
            key = match.group(1)
            return str(variables.get(key, match.group(0)))
        
        # Resolve recursively (for nested variables)
        limit = 5
        while "{{" in text and limit > 0:
            text = pattern.sub(replace, text)
            limit -= 1
        return text

    def _get_variables_dict(self, collection_path, environment_path=None):
        """Merges variables from collection and environment."""
        variables = {}
        try:
            # Collection variables
            with open(collection_path, 'r', encoding='utf-8') as f:
                col_data = json.load(f)
                for v in col_data.get('variable', []):
                    variables[v.get('key')] = v.get('value')
            
            # Environment variables
            if environment_path and os.path.exists(environment_path):
                with open(environment_path, 'r', encoding='utf-8') as f:
                    env_data = json.load(f)
                    for v in env_data.get('values', []):
                        if v.get('enabled', True):
                            variables[v.get('key')] = v.get('value')
        except Exception as e:
            log.error(f"Error loading variables: {e}")
        return variables

    def run_request(self, request_data, environment_path=None, custom_script=None):
        """
        Executes a Postman request natively using Python requests.
        No Newman required.
        """
        try:
            # 1. Load context
            variables = self._get_variables_dict(request_data['collection_path'], environment_path)
            
            with open(request_data['collection_path'], 'r', encoding='utf-8') as f:
                original = json.load(f)
            
            def find_item(items, name):
                for i in items:
                    if i.get('name') == name and 'request' in i: return i
                    if 'item' in i:
                        res = find_item(i['item'], name)
                        if res: return res
                return None
            
            item = find_item(original.get('item', []), request_data['name'])
            if not item: return None
            
            req_data = item.get('request', {})
            method = req_data.get('method', 'GET')
            
            # 2. Resolve URL
            raw_url = req_data.get('url', '')
            if isinstance(raw_url, dict): raw_url = raw_url.get('raw', '')
            url = self._resolve_variables(raw_url, variables)
            
            # 3. Resolve Headers
            headers = {}
            for h in req_data.get('header', []):
                if not h.get('disabled', False):
                    key = self._resolve_variables(h.get('key'), variables)
                    val = self._resolve_variables(h.get('value'), variables)
                    headers[key] = val
            
            # 4. Resolve Body
            body = None
            mode = req_data.get('body', {}).get('mode')
            if mode == 'raw':
                body = self._resolve_variables(req_data.get('body', {}).get('raw', ''), variables)
            elif mode == 'urlencoded':
                body = {self._resolve_variables(p.get('key'), variables): self._resolve_variables(p.get('value'), variables) 
                        for p in req_data.get('body', {}).get('urlencoded', [])}

            # 5. Execute
            log.info(f"Executing In-House: {method} {url}")
            res = requests.request(method, url, headers=headers, data=body, timeout=30, verify=False)
            
            # 6. Extract Header
            cid = res.headers.get('x-correlation-id')
            if cid:
                log.info(f"Extracted Correlation ID: {cid}")
                return cid
            
            # Check other casings just in case
            for k, v in res.headers.items():
                if k.lower() == 'x-correlation-id':
                    return v

        except Exception as e:
            log.error(f"In-House execution failed: {e}")
        
        return None
