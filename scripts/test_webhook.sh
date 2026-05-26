#!/bin/bash

BASE_URL=http://localhost:8000

# echo "=== 1. Wazuh Webhook ??? SSH Brute Force ==="
# curl -s -X POST "$BASE_URL/webhook/wazuh" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "data": {
#       "id": "test-alert-001",
#       "timestamp": "2026-05-20T10:30:00Z",
#       "rule": {
#         "id": "5710",
#         "name": "SSH Brute Force Attack",
#         "level": 7,
#         "description": "Multiple failed SSH login attempts detected",
#         "category": "authentication"
#       },
#       "srcip": "192.168.1.111",
#       "dstip": "10.0.0.5",
#       "srcport": 54321,
#       "dstport": 22,
#       "user": "root",
#       "protocol": "tcp",
#       "full_log": "SSHD: 5 failed login attempts from 192.168.1.100 to user root"
#     }
#   }'
# echo

# echo "=== 2. Generic Webhook ??? SQL Injection (web-exploit) ==="
# curl -s -X POST "$BASE_URL/webhook/generic" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "timestamp": "2026-05-20T11:00:00Z",
#     "event_id": "test-alert-002",
#     "rule_name": "SQL Injection Attempt",
#     "rule_level": 10,
#     "rule_description": "Possible SQL injection in login form",
#     "source_ip": "203.0.113.42",
#     "destination_ip": "10.0.0.10",
#     "destination_port": 443,
#     "message": "SQL injection detected: /api/login?user=admin&pass=1%27+OR+%271%27%3D%271"
#   }'
# echo

# echo "=== 3. Generic Webhook ??? Malware Detected (malware) ==="
# curl -s -X POST "$BASE_URL/webhook/generic" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "timestamp": "2026-05-20T11:05:00Z",
#     "event_id": "test-alert-003",
#     "rule_name": "Malware Signature Detected",
#     "rule_level": 12,
#     "rule_description": "Known malware signature in file download",
#     "source_ip": "45.33.32.156",
#     "destination_ip": "10.0.0.20",
#     "destination_port": 443,
#     "user_name": "jdoe",
#     "process_name": "chrome.exe",
#     "message": "Antivirus alert: EICAR test pattern detected in /downloads/setup.exe from 45.33.32.156"
#   }'
# echo

# echo "=== 4. Generic Webhook ??? Port Scan (reconnaissance) ==="
# curl -s -X POST "$BASE_URL/webhook/generic" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "timestamp": "2026-05-20T11:10:00Z",
#     "event_id": "test-alert-004",
#     "rule_name": "Port Scan Detected",
#     "rule_level": 5,
#     "rule_description": "Possible port scan from external IP",
#     "source_ip": "198.51.100.109",
#     "destination_ip": "10.0.0.1",
#     "protocol": "tcp",
#     "message": "Port scan detected: 100 ports scanned in 2 seconds from 198.51.100.109"
#   }'
# echo

# echo "=== 5. Generic Webhook ??? Unauthorized Access ==="
# curl -s -X POST "$BASE_URL/webhook/generic" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "timestamp": "2026-05-20T11:15:00Z",
#     "event_id": "test-alert-005",
#     "rule_name": "Suspicious Login from Unusual Location",
#     "rule_level": 8,
#     "rule_description": "User logged in from a country not in the allowlist",
#     "source_ip": "91.234.12.55",
#     "user_name": "admin",
#     "message": "Successful admin login from Moscow, RU (first time, source IP not in trusted list)"
#   }'
# echo

# echo "=== 6. Generic Webhook ??? Data Exfiltration ==="
# curl -s -X POST "$BASE_URL/webhook/generic" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "timestamp": "2026-05-20T11:20:00Z",
#     "event_id": "test-alert-006",
#     "rule_name": "Large Outbound Data Transfer",
#     "rule_level": 9,
#     "rule_description": "Unusual data transfer to external host",
#     "source_ip": "10.0.0.30",
#     "destination_ip": "185.220.101.15",
#     "destination_port": 443,
#     "user_name": "svc_backup",
#     "process_name": "curl",
#     "network_protocol": "tcp",
#     "message": "500 MB uploaded to 185.220.101.15 via HTTPS by svc_backup ??? exceeds 50 MB daily baseline"
#   }'
# echo

echo "=== 7. Wazuh Webhook ??? Malware (wazuh format) ==="
curl -s -X POST "$BASE_URL/webhook/wazuh" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "id": "test-alert-007",
      "timestamp": "2026-05-20T12:00:00Z",
      "rule": {
        "id": "8710",
        "name": "Malware Detected by FIM",
        "level": 12,
        "description": "File Integrity Monitoring detected malicious file creation",
        "category": "malware"
      },
      "srcip": "10.0.0.50",
      "dstip": "10.0.0.51",
      "user": "svc_web",
      "full_log": "FIM alert: /var/www/html/backdoor.php created ??? SHA256 matches known webshell signature"
    }
  }'
echo

# echo "=== 8. Wazuh Webhook ??? Web Exploit (wazuh format) ==="
# curl -s -X POST "$BASE_URL/webhook/wazuh" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "data": {
#       "id": "test-alert-008",
#       "timestamp": "2026-05-20T12:05:00Z",
#       "rule": {
#         "id": "31101",
#         "name": "Local File Inclusion Attempt",
#         "level": 10,
#         "description": "LFI attempt detected in HTTP request",
#         "category": "web"
#       },
#       "srcip": "185.220.101.20",
#       "dstip": "10.0.0.10",
#       "dstport": 80,
#       "protocol": "tcp",
#       "full_log": "HTTP request: GET /index.php?page=../../etc/passwd ??? LFI pattern detected"
#     }
#   }'
# echo

# echo "=== Done ??? 8 test alerts sent ==="
