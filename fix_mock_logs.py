import json
import random

with open('data/anypoint_monitoring_logs.json', 'r') as f:
    data = json.load(f)

apps = ["auth-api-v1.us-e1.cloudhub.io", "customer-sapi.us-e1.cloudhub.io"]
app_names = {"auth-api-v1.us-e1.cloudhub.io": "auth-api-v1", "customer-sapi.us-e1.cloudhub.io": "customer-sapi"}

if "responses" in data and data["responses"] and "hits" in data["responses"][0]:
    for i, hit in enumerate(data["responses"][0]["hits"].get("hits", [])):
        source = hit.get("_source", {})
        # Assign an app randomly
        app_id = apps[i % len(apps)]
        source["appId"] = app_id
        source["applicationName"] = app_names[app_id]
        
with open('data/anypoint_monitoring_logs.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Updated anypoint_monitoring_logs.json")
