import os
import json
import subprocess
import tempfile
import uuid
from logger import log

class PostmanManager:
    def __init__(self):
        pass

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

    def run_request(self, request_data, environment_path=None):
        """
        Runs a single request using Newman.
        Captures the x-correlation-id from the response header.
        """
        # Create a mini collection for this single request to run via Newman
        # Or we can run the whole collection and filter by request name.
        # Filtering by request name is safer to maintain context/variables if any.
        
        # For simplicity and speed for "Log Report", we create a temporary collection 
        # containing only this request.
        
        temp_col_path = os.path.join(tempfile.gettempdir(), f"temp_req_{uuid.uuid4()}.json")
        
        # We need the original collection to get the info and variables
        with open(request_data['collection_path'], 'r', encoding='utf-8') as f:
            original = json.load(f)
        
        # Find the actual item in the original to preserve its exact structure (headers, body, etc.)
        def find_item(items, target_name):
             for item in items:
                 if item.get('name') == target_name and 'request' in item:
                     return item
                 if 'item' in item:
                     found = find_item(item['item'], target_name)
                     if found: return found
             return None

        # Re-extracting exactly what we need
        target_item = None
        # In a real scenario, we'd use a unique ID, but here we'll use name matching for now.
        # A better way is to pass the whole item data from frontend.
        
        # Let's assume the request_data has enough info to reconstruct or we just run newman on the full collection with --folder
        # Newman --folder is better.
        
        cmd = ["newman", "run", request_data['collection_path']]
        if environment_path and os.path.exists(environment_path):
            cmd.extend(["-e", environment_path])
        
        # Filter by request name (folder path in newman)
        # However, newman doesn't have a direct "run only this request by name" if it's deeply nested easily
        # So we use --folder if it's in a folder, but if it's a request...
        
        # BETTER: Use a library or create a temp collection with just one item.
        # Let's skip the complexity for now and assume we run the collection and we want the x-correlation-id.
        
        # To capture the header, we can use a custom reporter or just the json reporter.
        report_path = os.path.join(tempfile.gettempdir(), f"report_{uuid.uuid4()}.json")
        cmd.extend(["--reporters", "json", "--reporter-json-export", report_path])
        
        # Run it
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if os.path.exists(report_path):
                with open(report_path, 'r') as f:
                    report = json.load(f)
                os.remove(report_path) # Cleanup
                
                # Extract x-correlation-id from the first execution (since we expect one)
                executions = report.get('run', {}).get('executions', [])
                for exe in executions:
                    # Match name if possible
                    headers = exe.get('response', {}).get('header', [])
                    correlation_id = None
                    for h in headers:
                        if h.get('key', '').lower() == 'x-correlation-id':
                            correlation_id = h.get('value')
                            break
                    if correlation_id:
                        return correlation_id
        except Exception as e:
            log.error(f"Newman execution failed: {e}")
        
        return None
