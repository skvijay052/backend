from datetime import datetime, timezone
from mimetypes import guess_extension
from pathlib import Path
from typing import Any, Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.core.supabase_client import get_response_data, get_supabase_admin_client
from app.schemas.photo import PhotoDeleteResult, ProfilePhotoListResponse, ProfilePhotoOut


router = APIRouter(prefix="/profiles", tags=["Profile Photos"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_photo(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["is_primary"] = bool(normalized.get("is_primary", False))
    return normalized


def _list_profile_photos(profile_id: str) -> list[dict[str, Any]]:
    response = (
        get_supabase_admin_client()
        .table(settings.profile_photos_table)
        .select("*")
        .eq("profile_id", profile_id)
        .order("is_primary", desc=True)
        .order("created_at")
        .execute()
    )
    return [_normalize_photo(row) for row in (get_response_data(response) or [])]


def _get_photo_by_id(photo_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_admin_client()
        .table(settings.profile_photos_table)
        .select("*")
        .eq("id", photo_id)
        .execute()
    )
    rows = get_response_data(response) or []
    return _normalize_photo(rows[0]) if rows else None


def _upsert_profile_image(profile_id: str, image_url: str | None) -> None:
    (
        get_supabase_admin_client()
        .table(settings.profiles_table)
        .upsert(
            {
                "id": profile_id,
                "image": image_url,
                "updated_at": _utc_now_iso(),
            }
        )
        .execute()
    )


def _sync_primary_photo(profile_id: str) -> dict[str, Any] | None:
    photos = _list_profile_photos(profile_id)
    if not photos:
        _upsert_profile_image(profile_id, None)
        return None

    primary_photo = next((photo for photo in photos if photo.get("is_primary")), photos[0])
    if not primary_photo.get("is_primary"):
        (
            get_supabase_admin_client()
            .table(settings.profile_photos_table)
            .update({"is_primary": True, "updated_at": _utc_now_iso()})
            .eq("id", primary_photo["id"])
            .execute()
        )
        primary_photo["is_primary"] = True

    _upsert_profile_image(profile_id, primary_photo["image_url"])
    return primary_photo


def _ensure_single_primary(profile_id: str, photo_id: str) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    client = get_supabase_admin_client()
    (
        client.table(settings.profile_photos_table)
        .update({"is_primary": False, "updated_at": now_iso})
        .eq("profile_id", profile_id)
        .execute()
    )
    response = (
        client.table(settings.profile_photos_table)
        .update({"is_primary": True, "updated_at": now_iso})
        .eq("id", photo_id)
        .execute()
    )
    rows = get_response_data(response) or []
    primary_photo = _normalize_photo(rows[0]) if rows else _get_photo_by_id(photo_id)
    if primary_photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found after updating primary photo.",
        )
    _upsert_profile_image(profile_id, primary_photo["image_url"])
    return primary_photo


def _ensure_storage_bucket() -> None:
    storage_client = get_supabase_admin_client().storage
    try:
        storage_client.get_bucket(settings.profile_photos_bucket)
        return
    except Exception:
        pass

    try:
        storage_client.create_bucket(
            settings.profile_photos_bucket,
            options={
                "public": True,
                "file_size_limit": 10 * 1024 * 1024,
                "allowed_mime_types": [
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                    "image/heic",
                    "image/heif",
                ],
            },
        )
    except Exception:
        # Another request may have created the bucket already.
        storage_client.get_bucket(settings.profile_photos_bucket)


def _guess_storage_extension(upload: UploadFile) -> str:
    file_name = upload.filename or ""
    suffix = Path(file_name).suffix
    if suffix:
        return suffix.lower()

    content_type = (upload.content_type or "").strip().lower()
    guessed = guess_extension(content_type, strict=False)
    if guessed:
        return guessed.lower()

    return ".jpg"


def _make_storage_path(profile_id: str, upload: UploadFile) -> str:
    return f"{profile_id}/{uuid4().hex}{_guess_storage_extension(upload)}"


@router.get("/me/photos", response_model=ProfilePhotoListResponse)
def list_my_photos(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfilePhotoListResponse:
    photos = _list_profile_photos(current_user.id)
    return ProfilePhotoListResponse(count=len(photos), items=[ProfilePhotoOut(**photo) for photo in photos])


@router.get("/{profile_id}/photos", response_model=ProfilePhotoListResponse)
def list_profile_photos(
    profile_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfilePhotoListResponse:
    del current_user
    photos = _list_profile_photos(profile_id)
    return ProfilePhotoListResponse(count=len(photos), items=[ProfilePhotoOut(**photo) for photo in photos])


@router.post("/me/photos", response_model=ProfilePhotoOut, status_code=status.HTTP_201_CREATED)
async def upload_my_photo(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ProfilePhotoOut:
    existing_photos = _list_profile_photos(current_user.id)
    if len(existing_photos) >= settings.max_profile_photos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You can upload up to {settings.max_profile_photos} photos.",
        )

    content_type = (file.content_type or "").strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image uploads are supported.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded photo is empty.",
        )

    _ensure_storage_bucket()
    storage_path = _make_storage_path(current_user.id, file)
    storage_bucket = get_supabase_admin_client().storage.from_(settings.profile_photos_bucket)

    try:
        storage_bucket.upload(
            storage_path,
            file_bytes,
            {
                "content-type": content_type,
                "cache-control": "3600",
                "x-upsert": "false",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to upload photo to storage: {exc}",
        ) from exc

    image_url = storage_bucket.get_public_url(storage_path)
    payload = {
        "profile_id": current_user.id,
        "image_url": image_url,
        "storage_path": storage_path,
        "is_primary": len(existing_photos) == 0,
        "updated_at": _utc_now_iso(),
    }

    try:
        response = (
            get_supabase_admin_client()
            .table(settings.profile_photos_table)
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        storage_bucket.remove([storage_path])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to save photo metadata: {exc}",
        ) from exc

    rows = get_response_data(response) or []
    photo_row = _normalize_photo(rows[0]) if rows else None
    if photo_row is None:
        storage_bucket.remove([storage_path])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Photo upload completed but metadata could not be reloaded.",
        )

    if photo_row["is_primary"]:
        _upsert_profile_image(current_user.id, photo_row["image_url"])

    return ProfilePhotoOut(**photo_row)


@router.patch("/me/photos/{photo_id}/primary", response_model=ProfilePhotoOut)
def set_primary_photo(
    photo_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProfilePhotoOut:
    photo_row = _get_photo_by_id(photo_id)
    if photo_row is None or photo_row["profile_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found.",
        )

    primary_photo = _ensure_single_primary(current_user.id, photo_id)
    return ProfilePhotoOut(**primary_photo)


@router.delete("/me/photos/{photo_id}", response_model=PhotoDeleteResult)
def delete_my_photo(
    photo_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PhotoDeleteResult:
    photo_row = _get_photo_by_id(photo_id)
    if photo_row is None or photo_row["profile_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found.",
        )

    try:
        get_supabase_admin_client().storage.from_(settings.profile_photos_bucket).remove(
            [photo_row["storage_path"]]
        )
    except Exception:
        # If the storage object is already gone, we still want to remove the db row.
        pass

    (
        get_supabase_admin_client()
        .table(settings.profile_photos_table)
        .delete()
        .eq("id", photo_id)
        .execute()
    )

    remaining_primary = _sync_primary_photo(current_user.id)
    if remaining_primary is None:
        _upsert_profile_image(current_user.id, None)

    return PhotoDeleteResult(message="Photo deleted.")
