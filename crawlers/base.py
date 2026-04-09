from abc import ABC, abstractmethod
from typing import Any


class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self, **kwargs) -> list[Any]: ...

    @abstractmethod
    def normalize(self, raw: Any) -> Any: ...
