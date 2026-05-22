from abc import ABC, abstractmethod
from datetime import datetime

from agent.models.schemas import NormalizedAlert


class SiemClient(ABC):
    @abstractmethod
    async def fetch_alerts(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        filters: dict | None = None,
    ) -> list[NormalizedAlert]:
        ...

    @abstractmethod
    async def get_alert_by_id(self, alert_id: str) -> NormalizedAlert | None:
        ...

    @abstractmethod
    async def send_plan(self, alert_id: str, plan_data: dict) -> bool:
        ...

    @abstractmethod
    async def close(self):
        ...
