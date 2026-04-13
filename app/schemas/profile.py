from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def _strip_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_gender_label(value: str | None) -> str | None:
    cleaned = _strip_string(value)
    if cleaned is None:
        return None

    aliases = {
        "m": "male",
        "male": "male",
        "man": "male",
        "f": "female",
        "female": "female",
        "woman": "female",
    }
    return aliases.get(cleaned.lower(), cleaned.lower())


class ProfileBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("name", "full_name"),
    )
    phone: str | None = Field(default=None, max_length=30)
    gender: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=18, le=99)
    height: str | None = Field(default=None, max_length=30)
    religion: str | None = Field(default=None, max_length=80)
    education: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    caste: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    image: str | None = Field(default=None, max_length=500)
    is_online: bool | None = None

    @field_validator(
        "name",
        "phone",
        "gender",
        "height",
        "religion",
        "education",
        "title",
        "caste",
        "bio",
        "city",
        "state",
        "country",
        "image",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_string(value)

    @field_validator("gender", mode="after")
    @classmethod
    def normalize_gender(cls, value: str | None) -> str | None:
        return _normalize_gender_label(value)


class ProfileUpsert(ProfileBase):
    pass


class ProfilePreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_age_min: int | None = Field(default=None, ge=18, le=99)
    preferred_age_max: int | None = Field(default=None, ge=18, le=99)
    preferred_location: str | None = Field(default=None, max_length=120)
    preferred_state: str | None = Field(default=None, max_length=120)
    preferred_city: str | None = Field(default=None, max_length=120)
    preferred_district: str | None = Field(default=None, max_length=120)
    preferred_religion: str | None = Field(default=None, max_length=80)
    preferred_education: str | None = Field(default=None, max_length=120)
    preferred_profession: str | None = Field(default=None, max_length=120)
    preferred_caste: str | None = Field(default=None, max_length=80)

    @field_validator(
        "preferred_location",
        "preferred_state",
        "preferred_city",
        "preferred_district",
        "preferred_religion",
        "preferred_education",
        "preferred_profession",
        "preferred_caste",
        mode="before",
    )
    @classmethod
    def normalize_preference_text(cls, value: str | None) -> str | None:
        return _strip_string(value)

    @model_validator(mode="after")
    def validate_age_window(self) -> "ProfilePreferencesUpdate":
        if (
            self.preferred_age_min is not None
            and self.preferred_age_max is not None
            and self.preferred_age_min > self.preferred_age_max
        ):
            raise ValueError("preferred_age_min must be less than or equal to preferred_age_max")
        return self


class ProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str | None = Field(default=None, validation_alias=AliasChoices("name", "full_name"))
    age: int | None = None
    height: str | None = None
    title: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    bio: str | None = None
    image: str | None = None
    is_online: bool = False


class ProfileDetail(ProfileSummary):
    phone: str | None = None
    gender: str | None = None
    religion: str | None = None
    education: str | None = None
    caste: str | None = None
    preferred_age_min: int | None = None
    preferred_age_max: int | None = None
    preferred_location: str | None = None
    preferred_state: str | None = None
    preferred_city: str | None = None
    preferred_district: str | None = None
    preferred_religion: str | None = None
    preferred_education: str | None = None
    preferred_profession: str | None = None
    preferred_caste: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfileStats(BaseModel):
    matches: int = 0
    interests: int = 0
    declined: int = 0


class ProfileListResponse(BaseModel):
    count: int
    items: list[ProfileSummary]
