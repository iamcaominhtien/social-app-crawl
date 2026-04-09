import asyncio
import json
from pathlib import Path
from typing import Any

from storage.base import StorageBackend


class JsonStore(StorageBackend):
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.base_path / f"{key}.json").resolve()
        if not path.is_relative_to(self.base_path.resolve()):
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    async def save(self, key: str, data: Any) -> None:
        path = self._resolve(key)
        content = json.dumps(data, indent=2, default=str)
        await asyncio.to_thread(path.write_text, content, "utf-8")

    async def load(self, key: str) -> Any:
        path = self._resolve(key)
        if not path.exists():
            return None
        text = await asyncio.to_thread(path.read_text, "utf-8")
        return json.loads(text)
