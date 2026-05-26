import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

ANALYSIS_INDEX_TEMPLATE = "aisoc-analysis-*"

INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index": {
            "query.default_field": ["aisoc.summary", "aisoc.raw_markdown", "message"]
        }
    },
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "event_id": {"type": "keyword"},
            "rule_id": {"type": "keyword"},
            "rule_name": {"type": "text"},
            "rule_level": {"type": "integer"},
            "source_ip": {"type": "ip"},
            "destination_ip": {"type": "ip"},
            "user_name": {"type": "keyword"},
            "network_protocol": {"type": "keyword"},
            "message": {"type": "text"},
            "aisoc": {
                "properties": {
                    "alert_id": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "category_description": {"type": "text"},
                    "summary": {"type": "text"},
                    "steps_count": {"type": "integer"},
                    "steps": {
                        "type": "nested",
                        "properties": {
                            "order": {"type": "integer"},
                            "action": {"type": "keyword"},
                            "description": {"type": "text"},
                            "commands": {"type": "keyword"},
                            "expected_result": {"type": "text"}
                        }
                    },
                    "raw_markdown": {"type": "text"},
                    "duration_seconds": {"type": "float"},
                    "created_at": {"type": "date"}
                }
            }
        }
    }
}


class AgentIndexerClient:
    def __init__(self, url: str, user: str, password: str,
                 index_prefix: str = "aisoc-analysis-",
                 verify_ssl: bool = False):
        self.url = url.rstrip("/")
        self.user = user
        self.password = password
        self.index_prefix = index_prefix
        self._client = httpx.AsyncClient(
            verify=verify_ssl, timeout=30.0, auth=(user, password)
        )

    def _daily_index(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        return f"{self.index_prefix}{today}"

    async def ensure_index(self) -> bool:
        name = self._daily_index()
        try:
            resp = await self._client.head(f"{self.url}/{name}")
            if resp.status_code == 200:
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                logger.warning("Index check error: %s", e)

        try:
            resp = await self._client.put(f"{self.url}/{name}", json=INDEX_SETTINGS)
            if resp.is_success:
                logger.info("Created index %s", name)
                return True
            logger.warning("Failed to create index %s: %s", name, resp.text)
            return False
        except Exception as e:
            logger.error("Error creating index %s: %s", name, e)
            return False

    async def index_analysis(self, document: dict) -> bool:
        await self.ensure_index()
        index_name = self._daily_index()
        try:
            resp = await self._client.post(
                f"{self.url}/{index_name}/_doc",
                json=document,
            )
            if resp.is_success:
                logger.info("Indexed analysis doc %s", document.get("event_id", ""))
                return True
            logger.warning("Indexing failed: %s", resp.text)
            return False
        except Exception as e:
            logger.error("Error indexing document: %s", e)
            return False

    async def close(self):
        await self._client.aclose()