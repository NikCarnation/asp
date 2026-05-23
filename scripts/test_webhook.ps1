# Test PowerShell requests for AISOC Connector webhook endpoints

Write-Host "=== Testing Wazuh Webhook Endpoint ===" -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:8000/webhook/wazuh" -Method POST -ContentType "application/json" -Body @{
    data = @{
        id = "test-alert-001"
        timestamp = "2026-05-20T10:30:00Z"
        rule = @{
            id = "5710"
            name = "SSH Brute Force Attack"
            level = 7
            description = "Multiple failed SSH login attempts detected"
            category = "authentication"
        }
        srcip = "192.168.1.100"
        dstip = "10.0.0.5"
        srcport = 54321
        dstport = 22
        user = "root"
        protocol = "tcp"
        full_log = "SSHD: 5 failed login attempts from 192.168.1.100 to user root"
    }
} | ConvertTo-Json

Write-Host "`n=== Testing Generic Webhook Endpoint ===" -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:8000/webhook/generic" -Method POST -ContentType "application/json" -Body @{
    timestamp = "2026-05-20T10:30:00Z"
    event_id = "test-alert-002"
    event_kind = "alert"
    event_category = "network"
    event_type = "warning"
    event_severity = 5
    rule_id = "5320"
    rule_name = "Port Scan Detected"
    rule_level = 5
    rule_description = "Possible port scan from external IP"
    source_ip = "198.51.100.77"
    destination_ip = "10.0.0.1"
    network_protocol = "tcp"
    message = "Port scan detected: 100 ports scanned in 2 seconds"
} | ConvertTo-Json

Write-Host "`n=== Testing Direct Alert Endpoint ===" -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/alerts/direct" -Method POST -ContentType "application/json" -Body @{
    data = @{
        id = "test-alert-003"
        timestamp = "2026-05-20T10:35:00Z"
        rule = @{
            id = "91101"
            name = "Web Shell Detection"
            level = 12
            description = "Possible web shell upload detected"
            category = "web"
        }
        srcip = "203.0.113.50"
        dstip = "10.0.0.10"
        srcport = 44321
        dstport = 80
        protocol = "tcp"
        full_log = "POST /uploads/shell.php - suspicious file upload detected"
    }
} | ConvertTo-Json

Write-Host "`n=== Testing Health Check ===" -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET | ConvertTo-Json

Write-Host "`nDone!" -ForegroundColor Green
