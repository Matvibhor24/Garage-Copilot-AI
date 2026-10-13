"""Photo upload from the mechanic's phone. Body is the raw image (Content-Type image/jpeg|png|webp)."""

import uuid

from fastapi import APIRouter, Depends, Request

from app.auth import current_user
from app.services import photos

router = APIRouter(prefix="/api")


@router.post("/jobs/{job_id}/photos")
async def upload_photo(job_id: str, request: Request, request_id: str = "", who=Depends(current_user)):
    data = await request.body()
    content_type = request.headers.get("content-type", "").split(";")[0]
    out = photos.add_photo(who, who["garage_id"], request_id or uuid.uuid4().hex, job_id, data, content_type)
    return out | {"url": photos.photo_url(who["garage_id"], out["path"])}
