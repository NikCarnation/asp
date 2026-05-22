import logging
from datetime import datetime

import httpx
from agent.models.schemas import NormalizedAlert
from connector.siem_clients.base import SiemClient

logger = logging.getLogger(__name__)


FIELD_MAP = {
    "source_ip": "data.srcip",
    "destination_ip": "data.dstip",
    "rule_id": "rule.id",
    "rule_level_min": "rule.level",
    "rule_level_max": "rule.level",
    "protocol": "data.protocol",
    "user_name": "data.user",
    "agent_id": "agent.id",
    "agent_name": "agent.name",
    "location": "location",
    "rule_groups": "rule.groups",
    "rule_description": "rule.description",
    "full_log": "full_log",
}


def _build_es_filters(start_date, end_date, extra) -> list[dict]:
    result: list[dict] = []

    if start_date or end_date:
        r = {}
        if start_date:
            r["gte"] = start_date.isoformat()
        if end_date:
            r["lte"] = end_date.isoformat()
        result.append({"range": {"timestamp": r}})

    if not extra:
        return result

    for key, value in extra.items():
        if value is None:
            continue
        es_field = FIELD_MAP.get(key)
        if not es_field:
            logger.warning("Unknown filter: %s", key)
            continue

        if key.endswith("_min"):
            result.append({"range": {es_field: {"gte": value}}})
        elif key.endswith("_max"):
            result.append({"range": {es_field: {"lte": value}}})
        elif key in ("rule_description", "full_log"):
            result.append({"wildcard": {es_field: f"*{value}*"}})
        elif key == "rule_groups":
            vals = value if isinstance(value, list) else [value]
            result.append({"terms": {es_field: vals}})
        else:
            result.append({"term": {es_field: value}})

    return result


def _map_indexer_doc(hit: dict) -> NormalizedAlert:
    src = hit["_source"]
    rule = src.get("rule", {})
    data = src.get("data") or {}
    agent = src.get("agent") or {}

    ts = src.get("timestamp", "")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

    return NormalizedAlert(
        timestamp=ts,
        event_id=src.get("id") or hit["_id"],
        event_severity=rule.get("level", 0),
        rule_id=str(rule.get("id", "")),
        rule_name=rule.get("description", ""),
        rule_level=rule.get("level", 0),
        rule_description=rule.get("description", ""),
        source_ip=data.get("srcip"),
        source_port=int(data["srcport"]) if data.get("srcport") and str(data["srcport"]).isdigit() else None,
        destination_ip=data.get("dstip"),
        destination_port=int(data["dstport"]) if data.get("dstport") and str(data["dstport"]).isdigit() else None,
        user_name=data.get("user"),
        network_protocol=data.get("protocol"),
        message=src.get("full_log") or rule.get("description", ""),
        raw=src,
    )


class IndexerClient(SiemClient):
    def __init__(self, url: str, user: str, password: str,
                 index_prefix: str = "wazuh-alerts-4.x-",
                 verify_ssl: bool = False):
        self.url = url.rstrip("/")
        self.user = user
        self.password = password
        self.index_prefix = index_prefix
        self._client = httpx.AsyncClient(verify=verify_ssl, timeout=30.0,
                                         auth=(user, password))

    def _index_pattern(self) -> str:
        return f"{self.index_prefix}*"

    async def fetch_alerts(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        filters: dict | None = None,
    ) -> list[NormalizedAlert]:
        es_filters = _build_es_filters(start_date, end_date, filters or {})

        body = {
            "size": limit,
            "from": offset,
            "sort": [{"timestamp": {"order": "desc"}}],
            "query": {"bool": {"filter": es_filters}} if es_filters else {"match_all": {}},
        }

        logger.info("Indexer fetch: size=%d from=%d filters=%s", limit, offset, bool(es_filters))
        resp = await self._client.post(
            f"{self.url}/{self._index_pattern()}/_search",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        alerts = [_map_indexer_doc(h) for h in hits]
        logger.info("Indexer: got %d alerts", len(alerts))
        return alerts

    async def get_alert_by_id(self, alert_id: str) -> NormalizedAlert | None:
        logger.info("Indexer get alert by ID: %s", alert_id)
        resp = await self._client.get(
            f"{self.url}/{self._index_pattern()}/_search",
            params={"q": f"id:{alert_id}", "size": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            logger.warning("Alert %s not found in indexer", alert_id)
            return None
        return _map_indexer_doc(hits[0])

    async def send_plan(self, alert_id: str, plan_data: dict) -> bool:
        logger.info("Writing plan to alert %s in indexer", alert_id)
        try:
            resp = await self._client.post(
                f"{self.url}/{self._index_pattern()}/_update_by_query",
                json={
                    "query": {"term": {"id": alert_id}},
                    "script": {
                        "source": "ctx._source.plan = params.plan",
                        "params": {"plan": plan_data},
                        "lang": "painless",
                    },
                },
            )
            resp.raise_for_status()
            updated = resp.json().get("updated", 0)
            return updated > 0
        except Exception as e:
            logger.error("Failed to write plan to indexer: %s", e)
            return False

    async def close(self):
        await self._client.aclose()
