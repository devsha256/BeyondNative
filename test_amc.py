import sys
import os
sys.path.append(os.getcwd())
from mulesoft_module import MuleSoftManager
import db_utils

m = MuleSoftManager()
orgs = m.get_organizations()
if not orgs:
    print("No orgs")
    sys.exit(0)
org_id = orgs[0]['id']
envs = m.get_environments(org_id)
if not envs:
    print("No envs")
    sys.exit(0)
env_id = envs[0]['id']

print(f"Org: {org_id}, Env: {env_id}")

headers = m.get_headers()
url = f"https://anypoint.mulesoft.com/amc/application-manager/api/v2/organizations/{org_id}/environments/{env_id}/deployments"
res = m.http_session.get(url, headers=headers)
if res.status_code == 200:
    items = res.json().get('items', [])
    if items:
        app = items[0]
        print("AMC Bulk item keys:", app.keys())
        print("AMC target keys:", app.get('target', {}).keys())
        print("AMC application keys:", app.get('application', {}).keys())
        if 'ref' in app.get('application', {}):
            print("REF found in bulk application!")
        else:
            print("REF NOT found in bulk application.")
            
        print("Detailed fetch:")
        app_id = app['id']
        url2 = f"https://anypoint.mulesoft.com/amc/adam/api/organizations/{org_id}/environments/{env_id}/deployments/{app_id}"
        res2 = m.http_session.get(url2, headers=headers)
        if res2.status_code == 200:
            print("Detailed keys:", res2.json().keys())
            print("Detailed application keys:", res2.json().get('application', {}).keys())
        else:
            print("Detailed failed", res2.status_code, res2.text)
else:
    print("Failed AMC bulk", res.status_code, res.text)
