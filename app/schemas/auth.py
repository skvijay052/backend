from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.profile import ProfileDetail


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


class AuthSignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = Field(default=None, max_length=30)
    gender: str | None = Field(default=None, max_length=20)

    @field_validator("name", "email", "phone", "gender", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip_string(value)

    @field_validator("gender", mode="after")
    @classmethod
    def normalize_gender(cls, value: str | None) -> str | None:
        return _normalize_gender_label(value)


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return _strip_string(value)


class AuthUserOut(BaseModel):
    id: str
    email: str | None = None
    phone: str | None = None
    name: str | None = None


class AuthSessionOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None = None
    token_type: str


class AuthResult(BaseModel):
    message: str
    user: AuthUserOut
    session: AuthSessionOut | None = None
    profile: ProfileDetail | None = None
