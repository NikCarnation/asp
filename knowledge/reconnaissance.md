# Reconnaissance / Port Scan Analysis Playbook

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
- `ss -tun | grep <SOURCE_IP>`
- Review IDS logs for related alerts

## 5. Key Questions
- Is this a targeted or broad scan?
- Which services were probed?
- Preceded any exploitation attempt?
