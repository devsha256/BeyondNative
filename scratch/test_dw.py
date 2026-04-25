import sys
import os
import json

# Add current directory to path
sys.path.append(os.getcwd())

from dw_module import DataWeaveManager

def test_dw():
    dw = DataWeaveManager()
    inputs = {
        "payload": {
            "content": "{\"name\": \"World\"}",
            "type": "json"
        }
    }
    scripts = {
        "main.dwl": "%dw 2.0\noutput application/json\n---\n{ \"greeting\": \"Hello \" ++ payload.name }"
    }
    
    print("Testing DataWeave evaluation...")
    result = dw.evaluate(inputs, scripts)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_dw()
