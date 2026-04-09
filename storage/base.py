from abc import ABC, abstractmethod
from typing import Any


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, key: str, data: Any) -> None: ...

    @abstractmethod
    async def load(self, key: str) -> Any: ...
