import subprocess
import logging
import os

log = logging.getLogger('dw_module')

class DataWeaveManager:
    """Manages the execution and evaluation of DataWeave scripts via the local DW CLI."""
    
    def __init__(self):
        # The DW CLI 'dw' is expected to be in the system PATH.
        self.cmd = "dw"

    def evaluate(self, payload, script, input_type="json"):
        """
        Executes a DataWeave transformation without writing temporary files.
        Uses subprocess pipes to pass input and scripts via stdin.
        """
        try:
            # We map shortcuts (json, xml, csv) to proper MIME types
            mime_map = {
                "json": "application/json",
                "xml": "application/xml",
                "csv": "application/csv",
                "yaml": "application/yaml"
            }
            content_type = mime_map.get(input_type.lower(), "application/json")
            
            # Command Pattern: dw run --input payload=application/{type} -f -
            # '-f -' tells dw to read the script from stdin
            # We need to pass the payload as a file or secondary input? 
            # Actually, standard 'dw run' often expects the script as an argument or from stdin 
            # and inputs via flags.
            
            # Optimized Command: dw run --input payload=application/{type}
            # The script itself can be passed as a positional argument if it's small, 
            # but for robustness we'll use 'dw run' and pipe the script.
            
            command = [
                self.cmd, "run", 
                "--input", f"payload={content_type}",
                "-f", "-" # Read script from stdin
            ]
            
            log.debug(f"DW Execution: {' '.join(command)}")
            
            # We use subprocess.Popen to handle stdin/stdout/stderr
            # But wait, how do we pass both payload AND script?
            # In DW CLI, we can pass payload via --input or by piping. 
            # Strategy: Write the script to the stdin pipe, and pass the payload as a string or file reference.
            # Actually, let's use a temporary string for the script and pass payload via stdin?
            # Re-evaluating CLI: 'dw run [script]' reads input from stdin.
            
            # Alternative: Put the script in a variable and pass the payload through stdin.
            # command = [self.cmd, "run", "--input", f"payload={content_type}", script]
            
            # If we want NO disk I/O for sensitive data, we can't use temp files for payload either.
            # Let's try:
            # dw run -i payload=[payload_content] [script]
            # But payload can be large.
            
            # Most reliable for piping:
            # Echo payload | dw run --input payload=application/json [script]
            
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Join payload and script if needed, OR if 'dw run' supports multiple inputs.
            # Actually, the standard 'dw run' reads the PRIMARY input from stdin if no file is specified.
            # But since we want to pass the SCRIPT via stdin (-f -), we need another way for payload.
            
            # Correct Pattern for 'stdin script' + 'string payload':
            # We'll use the --input flag with the literal payload content if it's not too massive.
            # If it is massive, we'd need a temp file, but per req we use stdin. write.
            
            # Let's assume the script is via -f - and we pass payload content as a literal input arg.
            # Actually, a better 'dw' pattern is:
            # dw run "the script" -i payload=input.json
            
            # REFINED STRATEGY for no Disk I/O:
            # We will use the script as the command argument and pipe the payload to stdin.
            # Pattern: dw run --input payload=application/{type} "[script]"
            
            refined_command = [
                self.cmd, "run",
                "--input", f"payload=@-" # Read payload from stdin
            ]
            # The script is passed as the main argument
            refined_command.append(script)
            
            process = subprocess.Popen(
                refined_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(input=payload)
            
            if process.returncode == 0:
                return {"success": True, "output": stdout, "error": None}
            else:
                return {"success": False, "output": None, "error": stderr or "Unknown execution error"}
                
        except FileNotFoundError:
            log.error("DW CLI Error: 'dw' command not found in PATH.")
            return {"success": False, "output": None, "error": "DataWeave CLI ('dw') is not installed or not in PATH."}
        except Exception as e:
            log.error(f"DW Execution Exception: {e}")
            return {"success": False, "output": None, "error": str(e)}
