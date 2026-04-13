from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.profile import ProfileSummary


def _strip_message(value: str) -> str:
    return value.strip()


class ChatMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        cleaned = _strip_message(value)
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    sender_id: str
    receiver_id: str
    text: str = Field(validation_alias="body")
    is_read: bool = False
    created_at: datetime | None = None
    read_at: datetime | None = None
    direction: Literal["sent", "received"]


class ChatMessagesResponse(BaseModel):
    profile: ProfileSummary | None = None
    count: int
    items: list[ChatMessageOut]


class ChatThreadOut(BaseModel):
    profile: ProfileSummary | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    matched_at: datetime | None = None


class ChatListResponse(BaseModel):
    count: int
    items: list[ChatThreadOut]
