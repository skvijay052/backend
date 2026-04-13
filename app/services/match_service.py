from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_or_get_match(user_a_id: str, user_b_id: str) -> dict[str, Any]:
    user_one_id, user_two_id = sorted([user_a_id, user_b_id])
    payload = {
        "user_one_id": user_one_id,
        "user_two_id": user_two_id,
        "status": "matched",
        "matched_at": utc_now_iso(),
    }

    response = (
        get_supabase_admin_client()
        .table(settings.matches_table)
        .upsert(payload, on_conflict="user_one_id,user_two_id")
        .execute()
    )
    rows = get_response_data(response) or []
    return rows[0] if rows else payload


def mark_interest_pair_as_matched(user_a_id: str, user_b_id: str) -> None:
    payload = {
        "status": "matched",
        "updated_at": utc_now_iso(),
    }
    client = get_supabase_admin_client()

    (
        client.table(settings.interests_table)
        .update(payload)
        .eq("sender_id", user_a_id)
        .eq("receiver_id", user_b_id)
        .execute()
    )
    (
        client.table(settings.interests_table)
        .update(payload)
        .eq("sender_id", user_b_id)
        .eq("receiver_id", user_a_id)
        .execute()
    )


def finalize_match(user_a_id: str, user_b_id: str) -> dict[str, Any]:
    match_row = create_or_get_match(user_a_id, user_b_id)
    mark_interest_pair_as_matched(user_a_id, user_b_id)
    return match_row
