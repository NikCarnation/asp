from abc import ABC, abstractmethod
from typing import Any

from connector.normalizer.ecs import ECSAlert


class BaseNormalizer(ABC):
    @abstractmethod
    def normalize(self, raw_alert: Any) -> ECSAlert:
        ...

    @abstractmethod
    def can_handle(self, raw_alert: Any) -> bool:
        ...
