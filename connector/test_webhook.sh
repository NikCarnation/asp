#!/bin/bash

# Test CURL requests for AISOC Connector webhook endpoints

echo "=== Testing Wazuh Webhook Endpoint ==="
curl -X POST http://localhost:8000/webhook/wazuh \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "id": "test-alert-001",
      "timestamp": "2026-05-20T10:30:00Z",
      "rule": {
        "id": "5710",
        "name": "SSH Brute Force Attack",
        "level": 7,
        "description": "Multiple failed SSH login attempts detected",
        "category": "authentication"
      },
      "srcip": "192.168.1.100",
      "dstip": "10.0.0.5",
      "srcport": 54321,
      "dstport": 22,
      "user": "root",
      "protocol": "tcp",
      "full_log": "SSHD: 5 failed login attempts from 192.168.1.100 to user root"
    }
  }'

echo -e "\n\n=== Testing Generic Webhook Endpoint ==="
curl -X POST http://localhost:8000/webhook/generic \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-20T10:30:00Z",
    "event_id": "test-alert-002",
    "event_kind": "alert",
    "event_category": "network",
    "event_type": "warning",
    "event_severity": 5,
    "rule_id": "5320",
    "rule_name": "Port Scan Detected",
    "rule_level": 5,
    "rule_description": "Possible port scan from external IP",
    "source_ip": "198.51.100.77",
    "destination_ip": "10.0.0.1",
    "network_protocol": "tcp",
    "message": "Port scan detected: 100 ports scanned in 2 seconds"
  }'

echo -e "\n\nDone!"
