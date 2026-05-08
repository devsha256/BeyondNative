import json
import os
import random
from datetime import datetime, timedelta, timezone

os.makedirs('data', exist_ok=True)

base_time = int(datetime.now().timestamp() * 1000)

buckets = []
for i in range(30):
    ts = datetime.now() - timedelta(minutes=30-i)
    buckets.append({
        "key_as_string": ts.isoformat(),
        "key": base_time - (30-i)*60000,
        "doc_count": random.randint(1, 20)
    })

hits = []
correlation_ids = [f"corr-id-alpha-{i}" for i in range(10)]
levels = ["DEBUG", "INFO", "WARN", "ERROR"]

for i in range(200):
    cid = random.choice(correlation_ids)
    # Increase error probability slightly for testing
    lvl = random.choices(levels, weights=[40, 40, 10, 10])[0]
    hits.append({
        "_index": "active-583d11d1-1d73-434e",
        "_type": "es-logging-mapping",
        "_id": f"VoOFCJ4BD5A4hJD2sMJa-{i}",
        "_source": {
            "logger": "HikariPool",
            "timestamp": (datetime.now() - timedelta(minutes=random.randint(0,30))).isoformat() + "Z",
            "request_path": "/v1/logs",
            "source": "%{original_source}",
            "event": "event: ",
            "orgId": "5e35e1fa-c86f-4691-b626-1eb1db3f87c5",
            "masterOrgId": "583d11d1-1d73-434e",
            "workerId": f"vc-digital-sap-hana-sapi-dev-6f658f7897-{random.randint(100,999)}",
            "log-level": lvl,
            "correlationId": cid,
            "message": f"Sample operation log for process ID {i}. Status: {lvl}",
            "class": "HikariPool-1 housekeeper",
            "appId": "vc-digital-sap-hana-sapi-dev",
            "envId": "32a286be-2293-4f10"
        }
    })

data = {
    "responses": [
        {
            "took": 216,
            "timed_out": False,
            "_shards": {
                "total": 3928,
                "successful": 3928,
                "skipped": 3926,
                "failed": 0
            },
            "hits": {
                "total": 1790,
                "max_score": None,
                "hits": hits
            },
            "aggregations": {
                "2": {
                    "buckets": buckets
                }
            },
            "status": 200
        }
    ]
}

with open('data/anypoint_monitoring_logs.json', 'w') as f:
    json.dump(data, f, indent=2)
