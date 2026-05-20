# Unauthorized Access Analysis Playbook

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
- `last -10 <USER>`
- `ausearch -m USER_LOGIN -ts recent`
- `grep <USER> /var/log/auth.log`

## 5. Key Questions
- Was the access attempt successful?
- Is the user account compromised?
- What data was accessed/viewed?
- Is this an insider threat scenario?
