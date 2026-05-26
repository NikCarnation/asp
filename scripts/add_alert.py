#!/usr/bin/env python3

import argparse
import json
import uuid
from datetime import datetime, timezone

import httpx

INDEXER_URL = "https://localhost:9200"
INDEXER_USER = "admin"
INDEXER_PASS = "SecretPassword"
INDEX_PREFIX = "wazuh-alerts-4.x-"


def make_alert(rule_id: str = "5710", rule_level: int = 7,
               srcip: str = "192.168.1.100", dstip: str = "10.0.0.5") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "timestamp": now.isoformat(),
        "rule": {
            "id": rule_id,
            "level": rule_level,
            "description": "Multiple failed SSH login attempts detected",
            "groups": ["authentication_failed", "ssh"],
            "mitre": {
                "id": ["T1110"],
                "tactic": ["Credential Access"],
                "technique": ["Brute Force"],
            },
            "gdpr": ["IV_32.2"],
            "pci_dss": ["8.1.2"],
        },
        "agent": {
            "id": "001",
            "name": "ubuntu-agent",
            "ip": "10.0.0.5",
        },
        "manager": {"name": "wazuh-manager"},
        "data": {
            "srcip": srcip,
            "dstip": dstip,
            "srcport": "54321",
            "dstport": "22",
            "protocol": "tcp",
        },
        "full_log": f"SSHD: 5 failed login attempts from {srcip} to user root",
        "location": "/var/log/auth.log",
        "id": f"{int(now.timestamp() * 1000)}.{uuid.uuid4().hex[:6]}",
    }


def main():
    parser = argparse.ArgumentParser(description="Add alert to Wazuh indexer")
    parser.add_argument("--url", default=INDEXER_URL, help="Indexer URL")
    parser.add_argument("--user", default=INDEXER_USER)
    parser.add_argument("--password", default=INDEXER_PASS)
    parser.add_argument("--index", default=None,
                        help=f"Index name (default: {INDEX_PREFIX}YYYY.MM.DD)")
    parser.add_argument("--rule-id", default="5710")
    parser.add_argument("--level", type=int, default=7)
    parser.add_argument("--srcip", default="192.168.1.100")
    parser.add_argument("--dstip", default="10.0.0.5")
    parser.add_argument("--count", type=int, default=1, help="Number of alerts")
    args = parser.parse_args()

    index = args.index or f"{INDEX_PREFIX}{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"

    client = httpx.Client(verify=False, auth=(args.user, args.password), timeout=30)

    for i in range(args.count):
        alert = make_alert(args.rule_id, args.level, args.srcip, args.dstip)
        alert["id"] = f"{alert['id']}-{i}"

        resp = client.post(f"{args.url}/{index}/_doc", json=alert)
        resp.raise_for_status()
        result = resp.json()
        print(f"[{i+1}/{args.count}] indexed {result['_id']} -> {result['result']}")

    client.close()
    print(f"Done — {args.count} alert(s) added to {index}")


if __name__ == "__main__":
    main()
