import requests
import json
import time

s = requests.Session()
# Test auth to get org
res = s.post('http://127.0.0.1:5001/logs/api/auth/test')
if res.status_code != 200:
    print("Auth failed:", res.text)
    exit(1)

orgs = res.json().get('orgs', [])
if not orgs:
    print("No orgs found")
    exit(1)
org_id = orgs[0]['id']

# Get envs
res = s.get(f'http://127.0.0.1:5001/api/mule/envs/{org_id}')
envs = res.json()
if not envs:
    print("No envs found")
    exit(1)
env_id = envs[0]['id']

# Get apps
res = s.get(f'http://127.0.0.1:5001/logs/api/apps?org_id={org_id}&env_id={env_id}')
apps = res.json()
app_id = apps[0]['name'] if apps else 'all'

end_time = int(time.time() * 1000)
start_time = end_time - 15 * 60 * 1000

# Fetch logs
url = f'http://127.0.0.1:5001/logs/api/events?org_id={org_id}&env_id={env_id}&app_id={app_id}&startTime={start_time}&endTime={end_time}'
print("Fetching logs:", url)
res = s.get(url)
print("Status:", res.status_code)
print("Response:", res.text[:1000])

