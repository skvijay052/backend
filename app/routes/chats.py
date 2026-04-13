from datetime import datetime, timezone
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, get_current_user
from app.core.config import clamp_list_limit, settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.chat import (
    ChatListResponse,
    ChatMessageCreate,
    ChatMessageOut,
    ChatMessagesResponse,
    ChatThreadOut,
)
from app.schemas.profile import ProfileSummary


router = APIRouter(prefix="/chats", tags=["Chats"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_genderless_profile(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    profile_name_column = settings.profile_name_column.strip() or "name"

    if "name" not in normalized:
        if profile_name_column in normalized:
            normalized["name"] = normalized.get(profile_name_column)
        elif "full_name" in normalized:
            normalized["name"] = normalized.get("full_name")

    normalized["is_online"] = bool(normalized.get("is_online", False))
    return normalized


def _sort_match_pair(user_a_id: str, user_b_id: str) -> tuple[str, str]:
    user_one_id, user_two_id = sorted([user_a_id, user_b_id])
    return user_one_id, user_two_id


def _get_match_row(user_a_id: str, user_b_id: str) -> dict[str, Any] | None:
    user_one_id, user_two_id = _sort_match_pair(user_a_id, user_b_id)
    response = (
        get_supabase_admin_client()
        .table(settings.matches_table)
        .select("*")
        .eq("user_one_id", user_one_id)
        .eq("user_two_id", user_two_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return rows[0] if rows else None


def _ensure_matched(current_user_id: str, profile_id: str) -> dict[str, Any]:
    match_row = _get_match_row(current_user_id, profile_id)
    if match_row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can chat only with matched profiles.",
        )
    return match_row


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
    return {row["id"]: _normalize_genderless_profile(row) for row in rows}


def _fetch_direct_messages(sender_id: str, receiver_id: str) -> list[dict[str, Any]]:
    response = (
        get_supabase_admin_client()
        .table(settings.messages_table)
        .select("*")
        .eq("sender_id", sender_id)
        .eq("receiver_id", receiver_id)
        .order("created_at", desc=False)
        .execute()
    )
    return get_response_data(response) or []


def _fetch_conversation_rows(current_user_id: str, profile_id: str) -> list[dict[str, Any]]:
    sent_rows = _fetch_direct_messages(current_user_id, profile_id)
    received_rows = _fetch_direct_messages(profile_id, current_user_id)
    rows = [*sent_rows, *received_rows]
    rows.sort(key=lambda row: row.get("created_at") or "")
    return rows


def _mark_messages_read(sender_id: str, receiver_id: str) -> None:
    (
        get_supabase_admin_client()
        .table(settings.messages_table)
        .update(
            {
                "is_read": True,
                "read_at": _utc_now_iso(),
            }
        )
        .eq("sender_id", sender_id)
        .eq("receiver_id", receiver_id)
        .eq("is_read", False)
        .execute()
    )


def _serialize_message(row: dict[str, Any], current_user_id: str) -> ChatMessageOut:
    payload = dict(row)
    payload["direction"] = "sent" if row.get("sender_id") == current_user_id else "received"
    return ChatMessageOut(**payload)


@router.get("", response_model=ChatListResponse)
def list_chats(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=settings.default_list_limit, ge=1),
) -> ChatListResponse:
    limit = clamp_list_limit(limit)
    matches_response = (
        get_supabase_admin_client()
        .table(settings.matches_table)
        .select("*")
        .or_(f"user_one_id.eq.{current_user.id},user_two_id.eq.{current_user.id}")
        .order("matched_at", desc=True)
        .limit(limit)
        .execute()
    )
    match_rows = get_response_data(matches_response) or []

    counterpart_ids = [
        row["user_two_id"] if row["user_one_id"] == current_user.id else row["user_one_id"]
        for row in match_rows
    ]
    profile_map = _get_profile_map(counterpart_ids)

    sent_rows: list[dict[str, Any]] = []
    received_rows: list[dict[str, Any]] = []
    if counterpart_ids:
        sent_response = (
            get_supabase_admin_client()
            .table(settings.messages_table)
            .select("*")
            .eq("sender_id", current_user.id)
            .in_("receiver_id", counterpart_ids)
            .execute()
        )
        received_response = (
            get_supabase_admin_client()
            .table(settings.messages_table)
            .select("*")
            .eq("receiver_id", current_user.id)
            .in_("sender_id", counterpart_ids)
            .execute()
        )
        sent_rows = get_response_data(sent_response) or []
        received_rows = get_response_data(received_response) or []

    latest_message_by_profile: dict[str, dict[str, Any]] = {}
    unread_counts: dict[str, int] = {}

    for row in [*sent_rows, *received_rows]:
        counterpart_id = row["receiver_id"] if row["sender_id"] == current_user.id else row["sender_id"]
        previous_row = latest_message_by_profile.get(counterpart_id)
        if previous_row is None or (row.get("created_at") or "") > (previous_row.get("created_at") or ""):
            latest_message_by_profile[counterpart_id] = row

        if (
            row.get("receiver_id") == current_user.id
            and row.get("sender_id") == counterpart_id
            and not row.get("is_read", False)
        ):
            unread_counts[counterpart_id] = unread_counts.get(counterpart_id, 0) + 1

    items: list[ChatThreadOut] = []
    for match_row in match_rows:
        counterpart_id = (
            match_row["user_two_id"] if match_row["user_one_id"] == current_user.id else match_row["user_one_id"]
        )
        profile_row = profile_map.get(counterpart_id)
        latest_row = latest_message_by_profile.get(counterpart_id)
        items.append(
            ChatThreadOut(
                profile=ProfileSummary(**profile_row) if profile_row else None,
                last_message=latest_row.get("body") if latest_row else None,
                last_message_at=latest_row.get("created_at") if latest_row else None,
                unread_count=unread_counts.get(counterpart_id, 0),
                matched_at=match_row.get("matched_at"),
            )
        )

    items.sort(
        key=lambda item: (
            item.last_message_at.isoformat() if item.last_message_at else "",
            item.matched_at.isoformat() if item.matched_at else "",
        ),
        reverse=True,
    )

    return ChatListResponse(count=len(items), items=items)


@router.get("/{profile_id}/messages", response_model=ChatMessagesResponse)
def list_chat_messages(
    profile_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChatMessagesResponse:
    _ensure_matched(current_user.id, profile_id)
    profile_map = _get_profile_map([profile_id])
    profile_row = profile_map.get(profile_id)
    if profile_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    rows = _fetch_conversation_rows(current_user.id, profile_id)
    unread_incoming_rows = [
        row
        for row in rows
        if row.get("sender_id") == profile_id and row.get("receiver_id") == current_user.id and not row.get("is_read")
    ]
    if unread_incoming_rows:
        read_at = _utc_now_iso()
        _mark_messages_read(profile_id, current_user.id)
        for row in rows:
            if row.get("sender_id") == profile_id and row.get("receiver_id") == current_user.id:
                row["is_read"] = True
                row["read_at"] = row.get("read_at") or read_at

    items = [_serialize_message(row, current_user.id) for row in rows]
    return ChatMessagesResponse(
        profile=ProfileSummary(**profile_row),
        count=len(items),
        items=items,
    )


@router.post("/{profile_id}/messages", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
def create_chat_message(
    profile_id: str,
    payload: ChatMessageCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChatMessageOut:
    _ensure_matched(current_user.id, profile_id)
    profile_map = _get_profile_map([profile_id])
    if profile_id not in profile_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )

    response = (
        get_supabase_admin_client()
        .table(settings.messages_table)
        .insert(
            {
                "sender_id": current_user.id,
                "receiver_id": profile_id,
                "body": payload.text,
                "is_read": False,
            }
        )
        .execute()
    )
    rows = get_response_data(response) or []
    message_row = rows[0] if rows else None
    if message_row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Message send completed but the stored row could not be reloaded.",
        )

    return _serialize_message(message_row, current_user.id)
