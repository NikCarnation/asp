from pydantic import BaseModel


class Playbook(BaseModel):
    title: str
    category: str
    content: str
    source: str | None = None


BRUTE_FORCE_PLAYBOOK = Playbook(
    title="Brute Force Attack Response",
    category="brute-force",
    source="AISOC Knowledge Base",
    content="""# Brute Force Attack Analysis Playbook

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
- `ss -tan | grep :22 | wc -l` (check active SSH connections)

## 5. Key Questions
- Is the source IP known malicious?
- How many failed attempts?
- Were any successful logins from the same IP?
- What accounts were targeted?
""",
)

WEB_EXPLOIT_PLAYBOOK = Playbook(
    title="Web Application Exploit Response",
    category="web-exploit",
    source="AISOC Knowledge Base",
    content="""# Web Application Exploit Analysis Playbook

## 1. Initial Triage
- Review web server access logs for the suspicious request
- Check WAF/ModSecurity logs
- Identify the affected endpoint and parameters

## 2. Investigation
- Determine if the exploit was successful (check response codes, file creation)
- Review for webshell indicators (unusual processes, outbound connections)
- Check file integrity on the web server

## 3. Containment
- Take affected server offline if compromise confirmed
- Block attacking IP at WAF/IPS
- Review and patch vulnerable code

## 4. Commands
- `tail -100 /var/log/apache2/access.log | grep -E "(POST|GET).*\\.(php|jsp|asp)"`
- `find /var/www/html -name "*.php" -mmin -60 -type f`
- `lsof -i -P -n | grep ESTABLISHED | grep http`

## 5. Key Questions
- Was the payload OWASP Top 10 related (SQLi, XSS, LFI, RCE)?
- Any uploaded files?
- Outbound connections from web server?
- Was the vulnerability in a known CVE?
""",
)

MALWARE_PLAYBOOK = Playbook(
    title="Malware Infection Response",
    category="malware",
    source="AISOC Knowledge Base",
    content="""# Malware Infection Analysis Playbook

## 1. Initial Triage
- Isolate affected endpoint from network
- Identify malware hash/signature via AV/EDR
- Check if malware is known (search VirusTotal)

## 2. Investigation
- Review process tree and parent-child relationships
- Check persistence mechanisms (scheduled tasks, services, registry)
- Analyze network connections — C2 indicators
- Collect full memory image for deep analysis

## 3. Containment & Eradication
- Block C2 domains/IPs on firewall/proxy
- Remove persistence mechanisms
- Reimage affected host if necessary
- Scan adjacent systems for propagation

## 4. Commands
- `wmic process list brief` (Windows process list)
- `netstat -ano | findstr ESTABLISHED`
- `schtasks /query /fo LIST /v` (check scheduled tasks)
- `reg export HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run run.reg`

## 5. Key Questions
- How did the malware enter (email, download, removable media)?
- What is the infection vector?
- Has data been exfiltrated?
- Are other hosts affected?
""",
)

RECONNAISSANCE_PLAYBOOK = Playbook(
    title="Reconnaissance / Port Scan Response",
    category="reconnaissance",
    source="AISOC Knowledge Base",
    content="""# Reconnaissance Analysis Playbook

## 1. Verification
- Confirm scan type (port scan, directory brute-force, DNS enumeration)
- Check source IP history in SIEM
- Determine scanning intensity (ports, timing)

## 2. Analysis
- Correlate with other alerts from same source
- Check if scan targeted specific services
- Review IDS/IPS signatures triggered

## 3. Response
- Add source to blocklist if malicious
- Honeypot redirection if applicable
- Increase monitoring for follow-up exploitation attempts

## 4. Commands
- `tcpdump -nn -c 100 host <SOURCE_IP>`
- Check connection states: `ss -tun | grep <SOURCE_IP>`
- Review IDS logs for related alerts

## 5. Key Questions
- Is this a targeted or broad scan?
- Which services were probed?
- Preceded any exploitation attempt?
""",
)

UNAUTHORIZED_ACCESS_PLAYBOOK = Playbook(
    title="Unauthorized Access Response",
    category="unauthorized-access",
    source="AISOC Knowledge Base",
    content="""# Unauthorized Access Analysis Playbook

## 1. Verification
- Review access logs for the specific resource
- Verify user identity and authorization level
- Check if access was successful or blocked

## 2. Investigation
- Review user's recent activity history
- Check for compromised credentials (logins from unusual locations)
- Review privilege escalation attempts

## 3. Containment
- Disable affected user account if compromised
- Review and tighten access controls
- Enable additional logging on sensitive resources

## 4. Commands
- `last -10 <USER>` (user login history)
- `ausearch -m USER_LOGIN -ts recent` (audit log)
- `grep <USER> /var/log/auth.log` (auth log review)

## 5. Key Questions
- Was the access attempt successful?
- Is the user account compromised?
- What data was accessed/viewed?
- Is this an insider threat scenario?
""",
)

POLICY_VIOLATION_PLAYBOOK = Playbook(
    title="Policy Violation Response",
    category="policy-violation",
    source="AISOC Knowledge Base",
    content="""# Policy Violation Analysis Playbook

## 1. Verification
- Review the specific policy rule triggered
- Identify user and endpoint involved
- Check if it's a false positive

## 2. Investigation
- Review user's security awareness training status
- Check endpoint posture/compliance status
- Determine if violation was intentional

## 3. Response
- Notify user's manager
- Update DLP/policy rules if false positive
- Initiate disciplinary process if intentional

## 4. Key Questions
- What policy was violated?
- Was sensitive data involved?
- Is this a first offense or repeat?
- Was the violation accidental or intentional?
""",
)

ALL_PLAYBOOKS = [
    BRUTE_FORCE_PLAYBOOK,
    WEB_EXPLOIT_PLAYBOOK,
    MALWARE_PLAYBOOK,
    RECONNAISSANCE_PLAYBOOK,
    UNAUTHORIZED_ACCESS_PLAYBOOK,
    POLICY_VIOLATION_PLAYBOOK,
]


CATEGORY_PLAYBOOK_MAP: dict[str, Playbook] = {
    pb.category: pb for pb in ALL_PLAYBOOKS
}
