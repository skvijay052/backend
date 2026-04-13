from datetime import datetime, timezone
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, get_current_user
from app.core.config import clamp_list_limit, settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.profile import (
    ProfileDetail,
    ProfileListResponse,
    ProfilePreferencesUpdate,
    ProfileStats,
    ProfileSummary,
    ProfileUpsert,
)


router = APIRouter(prefix="/profiles", tags=["Profiles"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_profile_name_column() -> str:
    return settings.profile_name_column.strip() or "name"


def _normalize_profile(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    profile_name_column = _get_profile_name_column()

    if "name" not in normalized:
        if profile_name_column in normalized:
            normalized["name"] = normalized.get(profile_name_column)
        elif "full_name" in normalized:
            normalized["name"] = normalized.get("full_name")

    normalized["is_online"] = bool(normalized.get("is_online", False))
    return normalized


def _prepare_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(payload)
    name_value = prepared.pop("name", None)
    if name_value is not None:
        prepared[_get_profile_name_column()] = name_value
    return prepared


def _get_response_count(response: Any) -> int | None:
    count = getattr(response, "count", None)
    return count if isinstance(count, int) else None


def _get_profile_by_id(profile_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .select("*")
        .eq("id", profile_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return _normalize_profile(rows[0]) if rows else None


def _guess_default_name(current_user: CurrentUser) -> str:
    raw_user = current_user.raw_user or {}
    metadata = raw_user.get("user_metadata") or {}
    candidates = [
        metadata.get("full_name"),
        metadata.get("name"),
        metadata.get("display_name"),
        metadata.get("first_name"),
    ]
    if current_user.email:
        candidates.append(current_user.email.split("@", 1)[0])
    candidates.append(current_user.phone)

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return "New User"


def _guess_default_phone(current_user: CurrentUser) -> str | None:
    raw_user = current_user.raw_user or {}
    metadata = raw_user.get("user_metadata") or {}
    candidates = [
        current_user.phone,
        metadata.get("phone"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def _guess_default_gender(current_user: CurrentUser) -> str | None:
    raw_user = current_user.raw_user or {}
    metadata = raw_user.get("user_metadata") or {}
    candidate = metadata.get("gender")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


def _normalize_gender_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None

    gender_aliases = {
        "m": "male",
        "male": "male",
        "man": "male",
        "f": "female",
        "female": "female",
        "woman": "female",
    }
    return gender_aliases.get(normalized, normalized)


def _get_discover_gender(current_user: CurrentUser, profile: dict[str, Any] | None) -> str | None:
    profile = profile or {}
    current_gender = _normalize_gender_value(profile.get("gender")) or _normalize_gender_value(
        _guess_default_gender(current_user)
    )

    opposite_gender_by_gender = {
        "male": "female",
        "female": "male",
    }
    return opposite_gender_by_gender.get(current_gender)


def _apply_missing_identity_defaults(
    *,
    current_user: CurrentUser,
    existing_profile: dict[str, Any] | None,
    update_data: dict[str, Any],
) -> None:
    existing_profile = existing_profile or {}

    if not update_data.get("name") and not existing_profile.get("name"):
        update_data["name"] = _guess_default_name(current_user)

    if not update_data.get("phone") and not existing_profile.get("phone"):
        resolved_phone = _guess_default_phone(current_user)
        if resolved_phone:
            update_data["phone"] = resolved_phone

    if not update_data.get("gender") and not existing_profile.get("gender"):
        resolved_gender = _guess_default_gender(current_user)
        if resolved_gender:
            update_data["gender"] = resolved_gender


def _build_profile_query(
    *,
    viewer_id: str,
    age_min: int | None = None,
    age_max: int | None = None,
    country: str | None = None,
    state: str | None = None,
    religion: str | None = None,
    caste: str | None = None,
    city: str | None = None,
    district: str | None = None,
    education: str | None = None,
    profession: str | None = None,
    only_online: bool = False,
    limit: int = 20,
):
    query = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .select("*")
        .neq("id", viewer_id)
    )

    if age_min is not None:
        query = query.gte("age", age_min)
    if age_max is not None:
        query = query.lte("age", age_max)
    if country:
        query = query.ilike("country", f"%{country.strip()}%")
    if state:
        query = query.ilike("state", f"%{state.strip()}%")
    if religion:
        query = query.ilike("religion", f"%{religion.strip()}%")
    if caste:
        query = query.ilike("caste", f"%{caste.strip()}%")
    if city:
        query = query.ilike("city", f"%{city.strip()}%")
    if district:
        query = query.ilike("city", f"%{district.strip()}%")
    if education:
        query = query.ilike("education", f"%{education.strip()}%")
    if profession:
        query = query.ilike("title", f"%{profession.strip()}%")
    if only_online:
        query = query.eq("is_online", True)

    return query.limit(limit)


def _count_matches_for_user(user_id: str) -> int:
    response = (
        get_supabase_admin_client()
        .table(settings.matches_table)
        .select("id", count="exact")
        .or_(f"user_one_id.eq.{user_id},user_two_id.eq.{user_id}")
        .limit(1)
        .execute()
    )
    count = _get_response_count(response)
    if count is not None:
        return count
    return len(get_response_data(response) or [])


def _count_interests_for_user(user_id: str) -> int:
    sent_response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("id", count="exact")
        .eq("sender_id", user_id)
        .limit(1)
        .execute()
    )
    received_response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("id", count="exact")
        .eq("receiver_id", user_id)
        .neq("status", "withdrawn")
        .limit(1)
        .execute()
    )

    sent_count = _get_response_count(sent_response)
    received_count = _get_response_count(received_response)

    if sent_count is None:
        sent_count = len(get_response_data(sent_response) or [])
    if received_count is None:
        received_count = len(get_response_data(received_response) or [])

    return sent_count + received_count


def _count_declined_interests_for_user(user_id: str) -> int:
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("id", count="exact")
        .eq("status", "rejected")
        .or_(f"sender_id.eq.{user_id},receiver_id.eq.{user_id}")
        .limit(1)
        .execute()
    )
    count = _get_response_count(response)
    if count is not None:
        return count
    return len(get_response_data(response) or [])


@router.get("/me", response_model=ProfileDetail)
def get_my_profile(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    profile = _get_profile_by_id(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Create it first with PUT /api/v1/profiles/me.",
        )
    return profile


@router.get("/me/stats", response_model=ProfileStats)
def get_my_profile_stats(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfileStats:
    return ProfileStats(
        matches=_count_matches_for_user(current_user.id),
        interests=_count_interests_for_user(current_user.id),
        declined=_count_declined_interests_for_user(current_user.id),
    )


@router.put("/me", response_model=ProfileDetail)
def upsert_my_profile(
    payload: ProfileUpsert,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    existing_profile = _get_profile_by_id(current_user.id)
    update_data = payload.model_dump(exclude_unset=True)
    update_data["id"] = current_user.id
    update_data["updated_at"] = _utc_now_iso()

    _apply_missing_identity_defaults(
        current_user=current_user,
        existing_profile=existing_profile,
        update_data=update_data,
    )

    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .upsert(_prepare_profile_payload(update_data))
        .execute()
    )
    rows = get_response_data(response) or []
    if rows:
        return _normalize_profile(rows[0])

    stored_profile = _get_profile_by_id(current_user.id)
    if stored_profile is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile upsert completed but the stored row could not be reloaded.",
        )
    return stored_profile


@router.put("/preferences", response_model=ProfileDetail)
def update_my_preferences(
    payload: ProfilePreferencesUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    existing_profile = _get_profile_by_id(current_user.id)
    update_data = payload.model_dump(exclude_unset=True)
    update_data["id"] = current_user.id
    update_data["updated_at"] = _utc_now_iso()

    _apply_missing_identity_defaults(
        current_user=current_user,
        existing_profile=existing_profile,
        update_data=update_data,
    )

    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .upsert(_prepare_profile_payload(update_data))
        .execute()
    )
    rows = get_response_data(response) or []
    if rows:
        return _normalize_profile(rows[0])

    stored_profile = _get_profile_by_id(current_user.id)
    if stored_profile is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Preference update completed but the profile row could not be reloaded.",
        )
    return stored_profile


@router.get("/discover", response_model=ProfileListResponse)
def discover_profiles(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    only_online: bool = Query(default=False),
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> ProfileListResponse:
    limit = clamp_list_limit(limit)
    my_profile = _get_profile_by_id(current_user.id) or {}
    discover_gender = _get_discover_gender(current_user, my_profile)
    candidate_limit = min(max(limit * 5, limit), settings.max_list_limit)

    query = _build_profile_query(
        viewer_id=current_user.id,
        only_online=only_online,
        limit=candidate_limit,
    )
    response = query.execute()
    rows = [_normalize_profile(row) for row in (get_response_data(response) or [])]

    if discover_gender:
        rows = [
            row for row in rows if _normalize_gender_value(row.get("gender")) == discover_gender
        ]

    rows = rows[:limit]
    return ProfileListResponse(count=len(rows), items=[ProfileSummary(**row) for row in rows])


@router.get("/search", response_model=ProfileListResponse)
def search_profiles(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    age_min: int | None = Query(default=None, ge=18, le=99),
    age_max: int | None = Query(default=None, ge=18, le=99),
    country: str | None = Query(default=None),
    state: str | None = Query(default=None),
    religion: str | None = Query(default=None),
    caste: str | None = Query(default=None),
    city: str | None = Query(default=None),
    district: str | None = Query(default=None),
    education: str | None = Query(default=None),
    profession: str | None = Query(default=None),
    only_online: bool = Query(default=False),
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> ProfileListResponse:
    limit = clamp_list_limit(limit)
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="age_min must be less than or equal to age_max.",
        )

    my_profile = _get_profile_by_id(current_user.id) or {}
    discover_gender = _get_discover_gender(current_user, my_profile)
    candidate_limit = min(max(limit * 5, limit), settings.max_list_limit)

    response = _build_profile_query(
        viewer_id=current_user.id,
        age_min=age_min,
        age_max=age_max,
        country=country,
        state=state,
        religion=religion,
        caste=caste,
        city=city,
        district=district,
        education=education,
        profession=profession,
        only_online=only_online,
        limit=candidate_limit,
    ).execute()
    rows = [_normalize_profile(row) for row in (get_response_data(response) or [])]

    if discover_gender:
        rows = [
            row for row in rows if _normalize_gender_value(row.get("gender")) == discover_gender
        ]

    rows = rows[:limit]
    return ProfileListResponse(count=len(rows), items=[ProfileSummary(**row) for row in rows])


@router.get("/{profile_id}", response_model=ProfileDetail)
def get_profile_by_id(
    profile_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    del current_user

    profile = _get_profile_by_id(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )
    return profile
