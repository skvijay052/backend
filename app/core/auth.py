from dataclasses import dataclass
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase_client import get_supabase_admin_client


bearer_scheme = HTTPBearer(auto_error=False)
TOKEN_CACHE_TTL_SECONDS = 120.0
_token_cache: dict[str, tuple[float, "CurrentUser"]] = {}


@dataclass(slots=True)
class CurrentUser:
    id: str
    email: str | None = None
    phone: str | None = None
    raw_user: dict[str, Any] | None = None


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _read_attr(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _get_cached_user(access_token: str) -> CurrentUser | None:
    cached = _token_cache.get(access_token)
    if cached is None:
        return None

    expires_at, current_user = cached
    if monotonic() >= expires_at:
        _token_cache.pop(access_token, None)
        return None

    return current_user


def _cache_user(access_token: str, current_user: CurrentUser) -> None:
    _token_cache[access_token] = (monotonic() + TOKEN_CACHE_TTL_SECONDS, current_user)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )

    cached_user = _get_cached_user(credentials.credentials)
    if cached_user is not None:
        return cached_user

    try:
        auth_response = get_supabase_admin_client().auth.get_user(credentials.credentials)
    except Exception as exc:  # pragma: no cover - depends on live Supabase
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unable to validate Supabase access token: {exc}",
        ) from exc

    user = _read_attr(auth_response, "user")
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase user could not be resolved from the provided token.",
        )

    user_dict = _as_dict(user)
    user_id = _read_attr(user, "id") or user_dict.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase user id is missing from the validated token.",
        )

    current_user = CurrentUser(
        id=str(user_id),
        email=_read_attr(user, "email") or user_dict.get("email"),
        phone=_read_attr(user, "phone") or user_dict.get("phone"),
        raw_user=user_dict,
    )
    _cache_user(credentials.credentials, current_user)
    return current_user
