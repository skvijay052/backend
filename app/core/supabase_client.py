from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.config import settings

try:
    from supabase.lib.client_options import SyncClientOptions as ClientOptions
except ImportError:  # pragma: no cover - compatibility fallback
    try:
        from supabase.lib.client_options import ClientOptions
    except ImportError:  # pragma: no cover - compatibility fallback
        try:
            from supabase.client import ClientOptions
        except ImportError:  # pragma: no cover - older client fallback
            ClientOptions = None


def _build_client(api_key: str) -> Client:
    if ClientOptions is None:
        return create_client(settings.supabase_url, api_key)

    return create_client(
        settings.supabase_url,
        api_key,
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def create_supabase_admin_client() -> Client:
    return _build_client(settings.supabase_service_role_key)


def create_supabase_anon_client() -> Client:
    return _build_client(settings.supabase_anon_key)


@lru_cache
def get_supabase_admin_client() -> Client:
    return create_supabase_admin_client()


@lru_cache
def get_supabase_anon_client() -> Client:
    return create_supabase_anon_client()


def get_response_data(response: Any) -> Any:
    return getattr(response, "data", response)
