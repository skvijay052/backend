from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.match import MatchOut
from app.schemas.profile import ProfileSummary


class InterestCreate(BaseModel):
    receiver_id: str = Field(min_length=1)


class InterestStatusUpdate(BaseModel):
    status: Literal["accepted", "rejected", "withdrawn"]


class InterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    sender_id: str
    receiver_id: str
    status: Literal["pending", "accepted", "rejected", "withdrawn", "matched"]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    direction: Literal["sent", "received"] | None = None
    profile: ProfileSummary | None = None


class InterestListResponse(BaseModel):
    count: int
    items: list[InterestOut]


class InterestMutationResult(BaseModel):
    interest: InterestOut
    match: MatchOut | None = None
