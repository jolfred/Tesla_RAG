from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Mention(BaseModel):
    id: str
    name: str
    raw: str


class Attachments(BaseModel):
    photos: list[str] = []
    links: list[str] = []
    docs: list[str] = []


class GroupContact(BaseModel):
    user_id: int
    name: str = ""
    role_title: str = ""
    profile_url: str = ""


class GroupMeta(BaseModel):
    domain: str
    group_id: int
    name: str
    description: str = ""
    status: str = ""
    members_count: int = 0
    site: str = ""
    verified: bool = False
    contacts: list[GroupContact] = []
    links: list[dict] = []


class SocialMediaPost(BaseModel):
    post_id: str | int
    source_platform: Literal["vk", "telegram"]
    group_id: str | int
    group_name: str
    group_domain: str | None = None
    post_url: str
    published_at: datetime
    text_raw: str
    text_clean: str
    hashtags: list[str] = []
    mentions: list[Mention] = []
    attachments: Attachments = Attachments()
