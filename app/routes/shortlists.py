from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, get_current_user
from app.core.config import clamp_list_limit, settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.profile import ProfileSummary
from app.schemas.shortlist import (
    ShortlistCreate,
    ShortlistDeleteResult,
    ShortlistListResponse,
    ShortlistOut,
)


router = APIRouter(prefix="/shortlists", tags=["Shortlists"])


def _normalize_profile(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    profile_name_column = settings.profile_name_column.strip() or "name"

    if "name" not in normalized:
        if profile_name_column in normalized:
            normalized["name"] = normalized.get(profile_name_column)
        elif "full_name" in normalized:
            normalized["name"] = normalized.get("full_name")

    normalized["is_online"] = bool(normalized.get("is_online", False))
    return normalized


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


def _get_profile_map(profile_ids: list[str]) -> dict[str, dict[str, Any]]:
    unique_ids = sorted(set(profile_ids))
    if not unique_ids:
        return {}

    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .select("*")
        .in_("id", unique_ids)
        .execute()
    )
    rows = get_response_data(response) or []
    return {row["id"]: _normalize_profile(row) for row in rows}


def _format_shortlist(row: dict[str, Any], profile_row: dict[str, Any] | None = None) -> ShortlistOut:
    return ShortlistOut(
        **row,
        profile=ProfileSummary(**profile_row) if profile_row else None,
    )


@router.get("/me", response_model=ShortlistListResponse)
def list_my_shortlists(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> ShortlistListResponse:
    limit = clamp_list_limit(limit)
    response = (
        get_supabase_admin_client()
        .table(settings.shortlists_table)
        .select("*")
        .eq("user_id", current_user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = get_response_data(response) or []
    profile_map = _get_profile_map([row["target_profile_id"] for row in rows])
    items = [_format_shortlist(row, profile_map.get(row["target_profile_id"])) for row in rows]
    return ShortlistListResponse(count=len(items), items=items)


@router.post("", response_model=ShortlistOut, status_code=status.HTTP_201_CREATED)
def create_shortlist(
    payload: ShortlistCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ShortlistOut:
    if payload.target_profile_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot shortlist your own profile.",
        )

    profile_row = _get_profile_by_id(payload.target_profile_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The target profile does not exist.",
        )

    response = (
        get_supabase_admin_client()
        .table(settings.shortlists_table)
        .upsert(
            {
                "user_id": current_user.id,
                "target_profile_id": payload.target_profile_id,
            },
            on_conflict="user_id,target_profile_id",
        )
        .execute()
    )
    rows = get_response_data(response) or []
    shortlist_row = rows[0] if rows else None
    if shortlist_row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shortlist save completed but the stored row could not be reloaded.",
        )

    return _format_shortlist(shortlist_row, profile_row)


@router.delete("/{target_profile_id}", response_model=ShortlistDeleteResult)
def delete_shortlist(
    target_profile_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ShortlistDeleteResult:
    (
        get_supabase_admin_client()
        .table(settings.shortlists_table)
        .delete()
        .eq("user_id", current_user.id)
        .eq("target_profile_id", target_profile_id)
        .execute()
    )
    return ShortlistDeleteResult(message="Removed from shortlist.")
