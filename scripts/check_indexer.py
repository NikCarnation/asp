#!/usr/bin/env python3
"""Check alerts in the Wazuh indexer (OpenSearch)."""

import httpx

INDEXER_URL = "https://localhost:9200"
INDEXER_USER = "admin"
INDEXER_PASS = "SecretPassword"
INDEX_PREFIX = "wazuh-alerts-4.x-"

from datetime import datetime, timezone

index = f"{INDEX_PREFIX}{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"

client = httpx.Client(verify=False, auth=(INDEXER_USER, INDEXER_PASS), timeout=30)

resp = client.post(
    f"{INDEXER_URL}/{index}/_search?size=5",
    json={"query": {"match_all": {}}},
)
resp.raise_for_status()
data = resp.json()

total = data["hits"]["total"]["value"]
print(f"Index: {index}")
print(f"Total alerts: {total}\n")

for hit in data["hits"]["hits"]:
    src = hit["_source"]
    print(f"  ID:      {hit['_id']}")
    print(f"  Rule:    #{src['rule']['id']} ({src['rule']['description']})")
    print(f"  Level:   {src['rule']['level']}")
    print(f"  Source:  {src['data'].get('srcip', '-')} -> {src['data'].get('dstip', '-')}")
    print(f"  Time:    {src['timestamp']}")
    print()

client.close()
