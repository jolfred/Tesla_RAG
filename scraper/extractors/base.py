from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime


class BaseExtractor(ABC):
    last_timestamp: datetime | None = None

    @abstractmethod
    def resolve_group(self, url_or_domain: str) -> dict:
        ...

    @abstractmethod
    def fetch_posts(self, limit: int, **kwargs) -> Iterable[dict]:
        ...
