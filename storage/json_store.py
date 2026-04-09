import json
from pathlib import Path
from typing import Any

from storage.base import StorageBackend


class JsonStore(StorageBackend):
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self.base_path / f"{key}.json"

    async def save(self, key: str, data: Any) -> None:
        path = self._resolve(key)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    async def load(self, key: str) -> Any:
        path = self._resolve(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
