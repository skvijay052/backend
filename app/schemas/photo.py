from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfilePhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    image_url: str
    storage_path: str
    is_primary: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfilePhotoListResponse(BaseModel):
    count: int
    items: list[ProfilePhotoOut]


class PhotoDeleteResult(BaseModel):
    message: str
