from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import ProfileSummary


class ShortlistCreate(BaseModel):
    target_profile_id: str = Field(min_length=1)


class ShortlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    user_id: str
    target_profile_id: str
    created_at: datetime | None = None
    profile: ProfileSummary | None = None


class ShortlistListResponse(BaseModel):
    count: int
    items: list[ShortlistOut]


class ShortlistDeleteResult(BaseModel):
    message: str
