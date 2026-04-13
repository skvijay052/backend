from typing import Any, Annotated

from fastapi import APIRouter, Depends, Query

from app.core.auth import CurrentUser, get_current_user
from app.core.config import clamp_list_limit, settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.match import MatchListResponse, MatchOut
from app.schemas.profile import ProfileSummary


router = APIRouter(prefix="/matches", tags=["Matches"])


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
    return {row["id"]: row for row in rows}


@router.get("", response_model=MatchListResponse)
def list_matches(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> MatchListResponse:
    limit = clamp_list_limit(limit)
    response = (
        get_supabase_admin_client()
        .table(settings.matches_table)
        .select("*")
        .or_(f"user_one_id.eq.{current_user.id},user_two_id.eq.{current_user.id}")
        .order("matched_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = get_response_data(response) or []

    counterpart_ids = [
        row["user_two_id"] if row["user_one_id"] == current_user.id else row["user_one_id"]
        for row in rows
    ]
    profile_map = _get_profile_map(counterpart_ids)

    items = []
    for row in rows:
        counterpart_id = row["user_two_id"] if row["user_one_id"] == current_user.id else row["user_one_id"]
        counterpart_profile = profile_map.get(counterpart_id)
        items.append(
            MatchOut(
                **row,
                profile=ProfileSummary(**counterpart_profile) if counterpart_profile else None,
            )
        )

    return MatchListResponse(count=len(items), items=items)
