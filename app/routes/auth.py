from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.supabase_client import (
    create_supabase_anon_client,
    get_supabase_admin_client,
)
from app.schemas.auth import (
    AuthLoginRequest,
    AuthResult,
    AuthSessionOut,
    AuthSignupRequest,
    AuthUserOut,
)
from app.schemas.profile import ProfileDetail


router = APIRouter(prefix="/auth", tags=["Auth"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_profile_name_column() -> str:
    return settings.profile_name_column.strip() or "name"


def _normalize_profile_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    profile_name_column = _get_profile_name_column()

    if "name" not in normalized:
        if profile_name_column in normalized:
            normalized["name"] = normalized.get(profile_name_column)
        elif "full_name" in normalized:
            normalized["name"] = normalized.get("full_name")

    return normalized


def _prepare_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(payload)
    name_value = prepared.pop("name", None)
    if name_value is not None:
        prepared[_get_profile_name_column()] = name_value
    return prepared


def _extract_name(user: Any, fallback_name: str | None = None) -> str | None:
    metadata = getattr(user, "user_metadata", None) or {}
    candidates = [
        fallback_name,
        metadata.get("full_name"),
        metadata.get("name"),
        metadata.get("display_name"),
        metadata.get("first_name"),
    ]
    email = getattr(user, "email", None)
    if email:
        candidates.append(email.split("@", 1)[0])

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_phone(user: Any, fallback_phone: str | None = None) -> str | None:
    metadata = getattr(user, "user_metadata", None) or {}
    candidates = [
        fallback_phone,
        getattr(user, "phone", None),
        metadata.get("phone"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _normalize_gender_label(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None

    aliases = {
        "m": "male",
        "male": "male",
        "man": "male",
        "f": "female",
        "female": "female",
        "woman": "female",
    }
    return aliases.get(normalized, normalized)


def _extract_gender(user: Any, fallback_gender: str | None = None) -> str | None:
    metadata = getattr(user, "user_metadata", None) or {}
    candidates = [
        fallback_gender,
        metadata.get("gender"),
    ]
    for candidate in candidates:
        normalized = _normalize_gender_label(candidate)
        if normalized:
            return normalized
    return None


def _get_profile_by_id(user_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .select("*")
        .eq("id", user_id)
        .execute()
    )
    rows = getattr(response, "data", response) or []
    return _normalize_profile_row(rows[0]) if rows else None


def _ensure_profile(
    *,
    user: Any,
    name: str | None = None,
    phone: str | None = None,
    gender: str | None = None,
) -> ProfileDetail | None:
    user_id = getattr(user, "id", None)
    if not user_id:
        return None

    payload: dict[str, Any] = {
        "id": user_id,
        "updated_at": _utc_now_iso(),
    }

    resolved_name = _extract_name(user, name)
    resolved_phone = _extract_phone(user, phone)
    resolved_gender = _extract_gender(user, gender)
    if resolved_name:
        payload["name"] = resolved_name
    if resolved_phone:
        payload["phone"] = resolved_phone
    if resolved_gender:
        payload["gender"] = resolved_gender

    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .upsert(_prepare_profile_payload(payload))
        .execute()
    )
    rows = getattr(response, "data", response) or []
    if rows:
        return ProfileDetail(**_normalize_profile_row(rows[0]))

    stored_profile = _get_profile_by_id(user_id)
    return ProfileDetail(**stored_profile) if stored_profile else None


def _serialize_session(session: Any | None) -> AuthSessionOut | None:
    if session is None:
        return None
    return AuthSessionOut(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        expires_at=session.expires_at,
        token_type=session.token_type,
    )


def _serialize_user(user: Any, fallback_name: str | None = None) -> AuthUserOut:
    return AuthUserOut(
        id=user.id,
        email=getattr(user, "email", None),
        phone=getattr(user, "phone", None),
        name=_extract_name(user, fallback_name),
    )


@router.post("/signup", response_model=AuthResult, status_code=status.HTTP_201_CREATED)
def signup(payload: AuthSignupRequest) -> AuthResult:
    try:
        auth_response = create_supabase_anon_client().auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {
                    "data": {
                        "full_name": payload.name,
                        "phone": payload.phone,
                        "gender": payload.gender,
                    }
                },
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Signup failed: {exc}",
        ) from exc

    if auth_response.user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed because Supabase did not return a user.",
        )

    profile = None
    if auth_response.session:
        profile = _ensure_profile(
            user=auth_response.user,
            name=payload.name,
            phone=payload.phone,
            gender=payload.gender,
        )

    message = (
        "Signup completed and user is logged in."
        if auth_response.session
        else "Signup completed. Email confirmation is still required."
    )

    return AuthResult(
        message=message,
        user=_serialize_user(auth_response.user, payload.name),
        session=_serialize_session(auth_response.session),
        profile=profile,
    )


@router.post("/login", response_model=AuthResult)
def login(payload: AuthLoginRequest) -> AuthResult:
    try:
        auth_response = create_supabase_anon_client().auth.sign_in_with_password(
            {
                "email": payload.email,
                "password": payload.password,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {exc}",
        ) from exc

    if auth_response.user is None or auth_response.session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login failed because Supabase did not return a valid session.",
        )

    profile = _ensure_profile(user=auth_response.user)

    return AuthResult(
        message="Login successful.",
        user=_serialize_user(auth_response.user),
        session=_serialize_session(auth_response.session),
        profile=profile,
    )
