from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Post(BaseModel):
    id: str
    platform: str
    content: str
    author_id: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
