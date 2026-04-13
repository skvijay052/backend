from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.profile import ProfileSummary


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    user_one_id: str
    user_two_id: str
    status: Literal["matched"] = "matched"
    matched_at: datetime | None = None
    created_at: datetime | None = None
    profile: ProfileSummary | None = None


class MatchListResponse(BaseModel):
    count: int
    items: list[MatchOut]
