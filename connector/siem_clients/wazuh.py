import logging
from datetime import datetime, timezone

import httpx
import os
from agent.models.schemas import NormalizedAlert
from connector.normalizer.ecs import normalize_wazuh_alert
from connector.siem_clients.base import SiemClient

logger = logging.getLogger(__name__)



class WazuhClient(SiemClient):
    def __init__(self, api_url: str, api_user: str, api_pass: str):
        self.api_url = api_url.rstrip("/")
        self.api_user = api_user
        self.api_pass = api_pass
        self._token: str | None = None
        self._client = httpx.AsyncClient(verify=False, timeout=30.0)

    async def _authenticate(self) -> str:
        logger.debug("Authenticating to Wazuh API %s", self.api_url)
        resp = await self._client.post(
            f"{self.api_url}/security/user/authenticate",
            auth=(self.api_user, self.api_pass),
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["data"]["token"] or os.getenv("TOKEN")
        logger.debug("Wazuh authentication successful")
        return self._token

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        if not self._token:
            await self._authenticate()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token}"
        url = f"{self.api_url}{path}"
        resp = await self._client.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 401:
            logger.info("Token expired, re-authenticating")
            await self._authenticate()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await self._client.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def fetch_alerts(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[NormalizedAlert]:
        params: dict = {"limit": limit, "offset": offset, "sort": "-timestamp"}
        filters = []
        if start_date:
            filters.append(f"timestamp>{start_date.isoformat()}")
        if end_date:
            filters.append(f"timestamp<{end_date.isoformat()}")
        if filters:
            params["q"] = ";".join(filters)

        logger.info("Fetching alerts: limit=%d offset=%d filters=%s", limit, offset, filters)
        result = await self._request("GET", "/security/alerts", params=params)
        items = result.get("data", {}).get("affected_items", [])
        alerts = [normalize_wazuh_alert(item) for item in items]
        logger.info("Fetched %d alerts from Wazuh", len(alerts))
        return alerts

    async def get_alert_by_id(self, alert_id: str) -> NormalizedAlert | None:
        logger.info("Getting alert by ID: %s", alert_id)
        result = await self._request(
            "GET",
            "/security/alerts",
            params={"limit": 1, "search": f"id={alert_id}"},
        )
        items = result.get("data", {}).get("affected_items", [])
        if items:
            return normalize_wazuh_alert(items[0])
        logger.warning("Alert %s not found", alert_id)
        return None

    async def send_plan(self, alert_id: str, plan_data: dict) -> bool:
        body = {
            "alert_id": alert_id,
            "plan": plan_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            logger.info("Sending plan for alert %s", alert_id)
            result = await self._request(
                "POST",
                "/security/alerts/context",
                json=body,
            )
            success = result.get("error") == 0
            logger.info("Plan sent successfully: %s", success)
            return success
        except Exception as e:
            logger.error("Failed to send plan: %s", e)
            return False

    async def close(self):
        await self._client.aclose()


# class MockWazuhClient(SiemClient):
#     def __init__(self):
#         self.alerts: list[NormalizedAlert] = self._generate_mock_alerts()
#         self.plans: dict[str, dict] = {}

#     def _generate_mock_alerts(self) -> list[NormalizedAlert]:
#         now = datetime.now(timezone.utc)
#         return [
#             NormalizedAlert(
#                 timestamp=now,
#                 event_id="alert-001",
#                 event_kind="alert",
#                 event_category="authentication",
#                 event_type="warning",
#                 event_severity=7,
#                 rule_id="5710",
#                 rule_name="SSH Brute Force Attack",
#                 rule_level=7,
#                 rule_description="Multiple failed SSH login attempts detected",
#                 source_ip="192.168.1.100",
#                 source_port=54321,
#                 destination_ip="10.0.0.5",
#                 destination_port=22,
#                 user_name="root",
#                 network_protocol="tcp",
#                 message="SSHD 5 failed login attempts from 192.168.1.100 to user root",
#                 raw={"data": {"rule": {"id": "5710", "name": "SSH Brute Force Attack", "level": 7}}},
#             ),
#             NormalizedAlert(
#                 timestamp=now,
#                 event_id="alert-002",
#                 event_kind="alert",
#                 event_category="web",
#                 event_type="critical",
#                 event_severity=12,
#                 rule_id="91101",
#                 rule_name="Web Shell Detection",
#                 rule_level=12,
#                 rule_description="Possible web shell upload detected",
#                 source_ip="203.0.113.50",
#                 source_port=44321,
#                 destination_ip="10.0.0.10",
#                 destination_port=80,
#                 network_protocol="tcp",
#                 message="POST /uploads/shell.php - suspicious file upload detected",
#                 raw={"data": {"rule": {"id": "91101", "name": "Web Shell Detection", "level": 12}}},
#             ),
#             NormalizedAlert(
#                 timestamp=now,
#                 event_id="alert-003",
#                 event_kind="alert",
#                 event_category="malware",
#                 event_type="critical",
#                 event_severity=15,
#                 rule_id="87100",
#                 rule_name="Malware Detected",
#                 rule_level=15,
#                 rule_description="Known malware signature detected on endpoint",
#                 source_ip="10.0.0.20",
#                 destination_ip="10.0.0.5",
#                 user_name="john.doe",
#                 process_name="powershell.exe",
#                 message="Malware 'Trojan.Generic' detected on host WS-001 in path C:\\Users\\john.doe\\Downloads\\invoice.exe",
#                 raw={"data": {"rule": {"id": "87100", "name": "Malware Detected", "level": 15}}},
#             ),
#             NormalizedAlert(
#                 timestamp=now,
#                 event_id="alert-004",
#                 event_kind="alert",
#                 event_category="network",
#                 event_type="info",
#                 event_severity=5,
#                 rule_id="5320",
#                 rule_name="Port Scan Detected",
#                 rule_level=5,
#                 rule_description="Possible port scan from external IP",
#                 source_ip="198.51.100.77",
#                 destination_ip="10.0.0.1",
#                 network_protocol="tcp",
#                 message="Port scan detected: 100 ports scanned in 2 seconds from 198.51.100.77",
#                 raw={"data": {"rule": {"id": "5320", "name": "Port Scan Detected", "level": 5}}},
#             ),
#             NormalizedAlert(
#                 timestamp=now,
#                 event_id="alert-005",
#                 event_kind="alert",
#                 event_category="compliance",
#                 event_type="warning",
#                 event_severity=8,
#                 rule_id="61101",
#                 rule_name="Unauthorized Access Attempt",
#                 rule_level=8,
#                 rule_description="User attempted to access restricted resource",
#                 source_ip="10.0.0.50",
#                 user_name="alice",
#                 process_name="chrome.exe",
#                 message="User alice attempted to access /admin/passwords.txt (HTTP 403)",
#                 raw={"data": {"rule": {"id": "61101", "name": "Unauthorized Access Attempt", "level": 8}}},
#             ),
#         ]

#     async def fetch_alerts(
#         self,
#         limit: int = 100,
#         offset: int = 0,
#         start_date: datetime | None = None,
#         end_date: datetime | None = None,
#     ) -> list[NormalizedAlert]:
#         result = self.alerts[offset : offset + limit]
#         if start_date:
#             result = [a for a in result if a.timestamp >= start_date]
#         if end_date:
#             result = [a for a in result if a.timestamp <= end_date]
#         return result

#     async def get_alert_by_id(self, alert_id: str) -> NormalizedAlert | None:
#         for a in self.alerts:
#             if a.event_id == alert_id:
#                 return a
#         return None

#     async def send_plan(self, alert_id: str, plan_data: dict) -> bool:
#         self.plans[alert_id] = plan_data
#         return True

#     async def close(self):
#         pass
