import socket
import subprocess
import json
import os
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class DataWeaveLSPManager:
    def __init__(self):
        self.enabled = os.environ.get('DW_LANG_SERVER_ENABLED', '').lower() == 'true'
        self.jar_path = self._find_jar()
        self.process = None
        self.f_in = None
        self.f_out = None
        self.msg_id = 0
        self.doc_version = 0
        self.error_logged = False
        self.lock = threading.Lock()
        
        # Hardcoded fallback
        self.static_snippets = [
            { "label": "map", "kind": 1, "snippet": "map ((item, index) -> $1)", "doc": "Iterates over items in an array and outputs the results into a new array." },
            { "label": "mapObject", "kind": 1, "snippet": "mapObject ((value, key, index) -> { (key): $1 })", "doc": "Iterates over an object using the key, value, and index of each element." },
            { "label": "filter", "kind": 1, "snippet": "filter ((item, index) -> $1)", "doc": "Returns an array that contains only the elements that satisfy a condition." },
            { "label": "reduce", "kind": 1, "snippet": "reduce ((item, acc = {}) -> $1)", "doc": "Applies a reduction expression to the elements in an array." },
            { "label": "groupBy", "kind": 1, "snippet": "groupBy ((item, index) -> $1)", "doc": "Returns an object that groups items from an array based on specified criteria." },
            { "label": "pluck", "kind": 1, "snippet": "pluck ((value, key, index) -> $1)", "doc": "Iterates over an object and returns an array of keys, values, or indices." },
            { "label": "flatten", "kind": 1, "snippet": "flatten($1)", "doc": "Flattens an array of arrays into a single, flat array." },
            { "label": "import Strings", "kind": 8, "snippet": "import * from dw::core::Strings\n", "doc": "DataWeave Strings module functions." },
            { "label": "import Arrays", "kind": 8, "snippet": "import * from dw::core::Arrays\n", "doc": "DataWeave Arrays module functions." }
        ]

    def _find_jar(self):
        base_dir = Path.home() / ".vscode" / "extensions"
        # The user requested: ~/.vscode/extensions/mulesoftinc.dataweave-*/server/data-weave-lang-server.jar
        # Or it might be in libs/data-weave-lang-server-all.jar
        for jar in base_dir.rglob("data-weave-lang-server*.jar"):
            if "mulesoftinc.dataweave" in str(jar):
                return str(jar)
        return None

    def start_lsp(self):
        if not self.enabled:
            return False
        if not self.jar_path:
            if not self.error_logged:
                print("[LSP] DataWeave Language Server JAR not found. Falling back to static snippets.")
                self.error_logged = True
            self.enabled = False
            return False
            
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind(('127.0.0.1', 0))
            server_socket.listen(1)
            port = server_socket.getsockname()[1]
            
            # The LSP jar uses a port argument and connects to it
            self.process = subprocess.Popen(["java", "-Xmx512m", "-jar", self.jar_path, str(port)])
            server_socket.settimeout(10.0)
            conn, _ = server_socket.accept()
            
            self.f_in = conn.makefile('r', encoding='utf-8')
            self.f_out = conn.makefile('w', encoding='utf-8')
            
            # Initialize request
            self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": None,
                "capabilities": {}
            }, wait_response=True)
            
            print(f"[LSP] Started DataWeave Language Server on port {port}")
            return True
        except Exception as e:
            if not self.error_logged:
                print(f"[LSP] Failed to start LSP process: {e}. Falling back to static snippets.")
                self.error_logged = True
            self.enabled = False
            if self.process:
                self.process.terminate()
            return False

    def _send_request(self, method, params, wait_response=False):
        self.msg_id += 1
        req_id = self.msg_id
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        if wait_response:
            req["id"] = req_id
            
        msg = json.dumps(req)
        payload = f"Content-Length: {len(msg)}\r\n\r\n{msg}"
        
        try:
            self.f_out.write(payload)
            self.f_out.flush()
        except Exception:
            return None
        
        if wait_response:
            while True:
                content_length = 0
                while True:
                    try:
                        header = self.f_in.readline()
                    except Exception:
                        return None
                    if not header:
                        return None
                    header = header.strip()
                    if not header:
                        break # End of headers
                    if header.startswith("Content-Length: "):
                        content_length = int(header.split(": ")[1])
                
                if content_length > 0:
                    body = self.f_in.read(content_length)
                    try:
                        resp = json.loads(body)
                        if resp.get("id") == req_id:
                            return resp
                    except json.JSONDecodeError:
                        return None

    def get_lsp_completions(self, context_code, line, character):
        if not self.enabled:
            return self.static_snippets
            
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                started = self.start_lsp()
                if not started:
                    return self.static_snippets

            # Use textDocument/didOpen or didChange to update the code
            doc_uri = "file:///temp.dwl"
            self.doc_version += 1
            
            if self.doc_version == 1:
                self._send_request("textDocument/didOpen", {
                    "textDocument": {
                        "uri": doc_uri,
                        "languageId": "dataweave",
                        "version": self.doc_version,
                        "text": context_code
                    }
                })
            else:
                self._send_request("textDocument/didChange", {
                    "textDocument": {
                        "uri": doc_uri,
                        "version": self.doc_version
                    },
                    "contentChanges": [{
                        "text": context_code
                    }]
                })
            
            # Give it a bit of time to parse
            time.sleep(0.1)
            
            # Completion request
            resp = self._send_request("textDocument/completion", {
                "textDocument": {"uri": doc_uri},
                "position": {"line": line, "character": character}
            }, wait_response=True)
            
            if resp and "result" in resp and resp["result"]:
                items = resp["result"].get("items", [])
                # Map LSP CompletionItem to Monaco format
                # kind mapping can be approximate
                suggestions = []
                for item in items:
                    suggestions.append({
                        "label": item.get("label"),
                        "kind": item.get("kind", 1),
                        "snippet": item.get("insertText", item.get("label")),
                        "doc": item.get("detail", "")
                    })
                return suggestions
                
            # fallback if no items
            return []
