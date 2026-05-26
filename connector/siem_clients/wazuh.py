import logging
from datetime import datetime, timezone

import httpx
from agent.models.schemas import NormalizedAlert
from connector.normalizer.ecs import normalize_wazuh_alert
from connector.siem_clients.base import SiemClient

logger = logging.getLogger(__name__)


class WazuhClient(SiemClient):
    def __init__(self, api_url: str, api_user: str, api_pass: str, verify_ssl: bool = False):
        self.api_url = api_url.rstrip("/")
        self.api_user = api_user
        self.api_pass = api_pass
        self.verify_ssl = verify_ssl
        self._token: str | None = None
        self._client = httpx.AsyncClient(verify=verify_ssl, timeout=30.0)

    async def _authenticate(self) -> str:
        auth_url = f"{self.api_url}/security/user/authenticate"
        try:
            response = await self._client.post(
                auth_url,
                auth=(self.api_user, self.api_pass),
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["data"]["token"]
            logger.info("wazuh_authentication_success")
            return self._token
        except httpx.HTTPError as e:
            logger.error("wazuh_authentication_failed", extra={"error": str(e), "url": auth_url})
            raise

    async def _ensure_token(self):
        if not self._token:
            await self._authenticate()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        await self._ensure_token()
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
        try:
            result = await self._request("GET", "/security/alerts", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Alerts endpoint not found on Wazuh API (404)")
                return []
            raise
        items = result.get("data", {}).get("affected_items", [])
        alerts = [normalize_wazuh_alert(item) for item in items]
        logger.info("Fetched %d alerts from Wazuh", len(alerts))
        return alerts

    async def get_alert_by_id(self, alert_id: str) -> NormalizedAlert | None:
        logger.info("Getting alert by ID: %s", alert_id)
        try:
            result = await self._request(
                "GET",
                "/security/alerts",
                params={"limit": 1, "q": f"id={alert_id}"},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Alert %s not found in Wazuh", alert_id)
                return None
            raise
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
            result = await self._request("POST", "/security/alerts/context", json=body)
            success = result.get("error") == 0
            logger.info("Plan sent successfully: %s", success)
            return success
        except Exception as e:
            logger.error("Failed to send plan: %s", e)
            return False

    async def close(self):
        await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            await self._ensure_token()
            response = await self._client.get(
                f"{self.api_url}/?pretty=true",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            logger.info("wazuh_health_check_passed")
            return True
        except Exception as e:
            logger.error("wazuh_health_check_failed", extra={"error": str(e)})
            return False
