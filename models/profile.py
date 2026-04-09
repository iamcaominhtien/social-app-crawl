from pydantic import BaseModel, Field


class Profile(BaseModel):
    id: str
    platform: str
    username: str
    display_name: str | None = None
    metadata: dict = Field(default_factory=dict)
