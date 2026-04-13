from datetime import datetime, timezone
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, get_current_user
from app.core.config import clamp_list_limit, settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.interest import (
    InterestCreate,
    InterestListResponse,
    InterestMutationResult,
    InterestOut,
    InterestStatusUpdate,
)
from app.schemas.match import MatchOut
from app.schemas.profile import ProfileSummary
from app.services.match_service import finalize_match


router = APIRouter(prefix="/interests", tags=["Interests"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _get_profile_by_id(profile_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .select("*")
        .eq("id", profile_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return rows[0] if rows else None


def _get_interest_by_id(interest_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("*")
        .eq("id", interest_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return rows[0] if rows else None


def _get_reciprocal_interest(sender_id: str, receiver_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("*")
        .eq("sender_id", sender_id)
        .eq("receiver_id", receiver_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return rows[0] if rows else None


def _format_interest(
    row: dict[str, Any],
    *,
    direction: str,
    profile_row: dict[str, Any] | None = None,
) -> InterestOut:
    profile = ProfileSummary(**profile_row) if profile_row else None
    return InterestOut(
        **row,
        direction=direction,  # type: ignore[arg-type]
        profile=profile,
    )


def _format_match(match_row: dict[str, Any] | None, profile_row: dict[str, Any] | None) -> MatchOut | None:
    if match_row is None:
        return None
    profile = ProfileSummary(**profile_row) if profile_row else None
    return MatchOut(**match_row, profile=profile)


@router.post("", response_model=InterestMutationResult, status_code=status.HTTP_201_CREATED)
def send_interest(
    payload: InterestCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> InterestMutationResult:
    if payload.receiver_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot send an interest to yourself.",
        )

    sender_profile = _get_profile_by_id(current_user.id)
    if sender_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete your own profile before sending interests.",
        )

    receiver_profile = _get_profile_by_id(payload.receiver_id)
    if receiver_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The target profile does not exist.",
        )

    interest_payload = {
        "sender_id": current_user.id,
        "receiver_id": payload.receiver_id,
        "status": "pending",
        "updated_at": _utc_now_iso(),
    }
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .upsert(interest_payload, on_conflict="sender_id,receiver_id")
        .execute()
    )
    rows = get_response_data(response) or []
    interest_row = rows[0] if rows else interest_payload

    reciprocal_interest = _get_reciprocal_interest(payload.receiver_id, current_user.id)
    match_row = None
    if reciprocal_interest and reciprocal_interest.get("status") in {"pending", "accepted", "matched"}:
        match_row = finalize_match(current_user.id, payload.receiver_id)
        interest_row = _get_interest_by_id(interest_row["id"]) if interest_row.get("id") else None
        interest_row = interest_row or {**interest_payload, "status": "matched"}

    return InterestMutationResult(
        interest=_format_interest(interest_row, direction="sent", profile_row=receiver_profile),
        match=_format_match(match_row, receiver_profile),
    )


@router.get("/received", response_model=InterestListResponse)
def list_received_interests(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> InterestListResponse:
    limit = clamp_list_limit(limit)
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("*")
        .eq("receiver_id", current_user.id)
        .neq("status", "withdrawn")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = get_response_data(response) or []
    profile_map = _get_profile_map([row["sender_id"] for row in rows])
    items = [
        _format_interest(row, direction="received", profile_row=profile_map.get(row["sender_id"]))
        for row in rows
    ]
    return InterestListResponse(count=len(items), items=items)


@router.get("/sent", response_model=InterestListResponse)
def list_sent_interests(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> InterestListResponse:
    limit = clamp_list_limit(limit)
    response = (
        get_supabase_admin_client()
        .table(settings.interests_table)
        .select("*")
        .eq("sender_id", current_user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = get_response_data(response) or []
    profile_map = _get_profile_map([row["receiver_id"] for row in rows])
    items = [
        _format_interest(row, direction="sent", profile_row=profile_map.get(row["receiver_id"]))
        for row in rows
    ]
    return InterestListResponse(count=len(items), items=items)


@router.patch("/{interest_id}", response_model=InterestMutationResult)
def update_interest_status(
    interest_id: str,
    payload: InterestStatusUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> InterestMutationResult:
    interest_row = _get_interest_by_id(interest_id)
    if interest_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interest not found.",
        )

    is_receiver = interest_row["receiver_id"] == current_user.id
    is_sender = interest_row["sender_id"] == current_user.id

    if payload.status in {"accepted", "rejected"} and not is_receiver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the receiving user can accept or reject an interest.",
        )

    if payload.status == "withdrawn" and not is_sender:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sending user can withdraw an interest.",
        )

    counterpart_id = interest_row["sender_id"] if is_receiver else interest_row["receiver_id"]
    counterpart_profile = _get_profile_by_id(counterpart_id)
    match_row = None

    if payload.status == "accepted":
        match_row = finalize_match(interest_row["sender_id"], interest_row["receiver_id"])
        updated_interest = _get_interest_by_id(interest_id) or {**interest_row, "status": "matched"}
    else:
        response = (
            get_supabase_admin_client()
            .table(settings.interests_table)
            .update(
                {
                    "status": payload.status,
                    "updated_at": _utc_now_iso(),
                }
            )
            .eq("id", interest_id)
            .execute()
        )
        rows = get_response_data(response) or []
        updated_interest = rows[0] if rows else {**interest_row, "status": payload.status}

    direction = "received" if updated_interest["receiver_id"] == current_user.id else "sent"
    return InterestMutationResult(
        interest=_format_interest(updated_interest, direction=direction, profile_row=counterpart_profile),
        match=_format_match(match_row, counterpart_profile),
    )
