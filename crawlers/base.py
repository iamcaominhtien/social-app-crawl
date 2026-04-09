from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from helpers.rate_limiter import RateLimiter

T = TypeVar("T")


class BaseCrawler(ABC, Generic[T]):
    def __init__(self, rate_limiter: RateLimiter) -> None:
        self.rate_limiter = rate_limiter

    @abstractmethod
    async def crawl(self, **kwargs) -> list[T]: ...

    @abstractmethod
    def normalize(self, raw: Any) -> T: ...
