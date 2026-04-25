import subprocess
import logging
import os
import tempfile
import json
import shutil

log = logging.getLogger('dw_module')

class DataWeaveManager:
    """Manages the execution and evaluation of DataWeave projects via the local DW CLI."""
    
    def __init__(self):
        # The DW CLI 'dw' is expected to be in the system PATH.
        self.cmd = "dw"

    def evaluate(self, inputs_map, scripts_map):
        """
        Executes a DataWeave transformation with support for multiple inputs and modular scripts.
        Creates a temporary project structure to allow DW to resolve internal modules/imports.
        """
        temp_dir = tempfile.mkdtemp(prefix="dw_workspace_")
        try:
            # 1. Setup Inputs
            # Inputs are stored in a dedicated 'inputs' folder within the temp workspace
            inputs_dir = os.path.join(temp_dir, "inputs")
            os.makedirs(inputs_dir)
            
            input_args = []
            for name, data in inputs_map.items():
                content = data.get('content', '')
                ext = data.get('type', 'json').lower()
                
                # Write input content to file
                input_file_path = os.path.join(inputs_dir, f"{name}.{ext}")
                with open(input_file_path, "w") as f:
                    f.write(content)
                
                # Map MIME type for DW
                mime_map = {
                    "json": "application/json",
                    "xml": "application/xml",
                    "csv": "application/csv",
                    "yaml": "application/yaml",
                    "dwl": "application/dwl",
                    "txt": "text/plain"
                }
                mime = mime_map.get(ext, f"application/{ext}")
                
                # Add to command: -i <name>=<path>
                input_args.extend(["-i", f"{name}={input_file_path}"])

            # 2. Setup Scripts (Modules)
            # Scripts are written to temp_dir, preserving subdirectory structures
            main_script_path = None
            for filename, content in scripts_map.items():
                if not filename.endswith(".dwl"):
                    filename += ".dwl"
                
                script_path = os.path.join(temp_dir, filename)
                # Ensure parent directory exists for modules in subfolders
                os.makedirs(os.path.dirname(script_path), exist_ok=True)
                
                with open(script_path, "w") as f:
                    f.write(content)
                
                # Check for entry point
                if filename == "main.dwl" or main_script_path is None:
                    main_script_path = script_path

            if not main_script_path:
                return {"success": False, "error": "No script files provided."}

            # 3. Orchestration and Execution
            # Command: dw run -i name=path/to/file --path . -f main_script
            # Note: We use --path . to include the local workspace in the library path for imports
            command = [self.cmd, "run"] + input_args + ["--path", ".", "-f", main_script_path]
            
            log.debug(f"DW Project Execution: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                return {"success": True, "output": stdout, "error": None}
            else:
                # DW CLI often dumps verbose errors to stderr
                # We attempt to clean it up for the UI
                return {"success": False, "output": None, "error": stderr or "Unknown execution error"}
                
        except FileNotFoundError:
            log.error("DW CLI Error: 'dw' command not found in PATH.")
            return {"success": False, "error": "DataWeave CLI ('dw') is not installed or not in PATH."}
        except Exception as e:
            log.error(f"DW Execution Exception: {e}")
            return {"success": False, "error": str(e)}
        finally:
            # Crucial: Clean up the sensitive data
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
