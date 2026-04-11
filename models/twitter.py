from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PostType(str, Enum):
    original = "original"
    repost = "repost"
    reply = "reply"


class TwitterPost(BaseModel):
    post_id: Optional[str] = None
    post_type: PostType
    author_username: str
    author_display_name: str
    date: Optional[datetime] = None
    content: str = ""
    media_urls: list[str] = Field(default_factory=list)
    likes: Optional[int] = None
    retweets: Optional[int] = None
    replies: Optional[int] = None
    views: Optional[int] = None
    post_url: str
    # Populated only when post_type == "repost"
    original_author_username: Optional[str] = None
    original_author_display_name: Optional[str] = None
    # Populated only when post_type == "reply"
    reply_to: Optional[str] = None
