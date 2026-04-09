from typing import Any

from pydantic import BaseModel, Field


class Profile(BaseModel):
    id: str
    platform: str
    username: str
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
