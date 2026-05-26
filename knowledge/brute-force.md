# Brute Force Attack Analysis Playbook

## 1. Initial Verification
- Check source IP reputation (VirusTotal, AbuseIPDB)
- Verify if authentication attempts were successful
- Review authentication logs for compromised accounts

## 2. Containment
- Block offending source IP on perimeter firewall
- Force password reset for affected accounts
- Enable MFA if not already active

## 3. Eradication
- Scan affected systems for malware
- Review and rotate all credentials accessed during the window
- Check for lateral movement indicators

## 4. Commands
- `grep "Failed password" /var/log/auth.log | awk '{print $11}' | sort | uniq -c | sort -nr`
- `journalctl -u sshd --since "1 hour ago" | grep "Failed password"`
- `ss -tan | grep :22 | wc -l`

## 5. Key Questions
- Is the source IP known malicious?
- How many failed attempts?
- Were any successful logins from the same IP?
- What accounts were targeted?
