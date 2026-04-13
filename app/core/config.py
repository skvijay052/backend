from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bandhanaa API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = True

    supabase_url: str = Field(validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(validation_alias="SUPABASE_SERVICE_ROLE_KEY")

    profiles_table: str = Field(default="profiles", validation_alias="PROFILES_TABLE")
    profile_photos_table: str = Field(default="profile_photos", validation_alias="PROFILE_PHOTOS_TABLE")
    interests_table: str = Field(default="interests", validation_alias="INTERESTS_TABLE")
    matches_table: str = Field(default="matches", validation_alias="MATCHES_TABLE")
    messages_table: str = Field(default="messages", validation_alias="MESSAGES_TABLE")
    shortlists_table: str = Field(default="shortlists", validation_alias="SHORTLISTS_TABLE")
    profile_name_column: str = Field(default="name", validation_alias="PROFILE_NAME_COLUMN")
    profile_photos_bucket: str = Field(default="profile-images", validation_alias="PROFILE_PHOTOS_BUCKET")
    max_profile_photos: int = Field(default=6, validation_alias="MAX_PROFILE_PHOTOS")

    default_list_limit: int = Field(default=20, validation_alias="DEFAULT_LIST_LIMIT")
    max_list_limit: int = Field(default=50, validation_alias="MAX_LIST_LIMIT")
    cors_origins_value: str = Field(default="", validation_alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        if not self.cors_origins_value:
            return []
        return [item.strip() for item in self.cors_origins_value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def clamp_list_limit(limit: int) -> int:
    return max(1, min(limit, settings.max_list_limit))
