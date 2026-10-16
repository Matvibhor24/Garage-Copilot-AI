"""Photo upload from the mechanic's phone (body: the raw image, Content-Type image/jpeg|png|webp; the app shrinks
it to a JPEG first), and the backend-served photo link used when Cloud Storage can't sign URLs (C21)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app import links, storage
from app.auth import current_user
from app.services import photos

router = APIRouter(prefix="/api")


@router.post("/jobs/{job_id}/photos")
async def upload_photo(job_id: str, request: Request, request_id: str = "", who=Depends(current_user)):
    data = await request.body()
    content_type = request.headers.get("content-type", "").split(";")[0]
    out = photos.add_photo(who, who["garage_id"], request_id or uuid.uuid4().hex, job_id, data, content_type)
    return out | {"url": photos.photo_url(who["garage_id"], out["path"])}


@router.get("/photos/{token}")
def photo(token: str):
    """The photo bytes for a short-lived signed token (no login: the token is the permission, like /j/{token})."""
    try:
        garage_id, path = links.read_photo_token(token)
    except links.BadLink as e:
        raise HTTPException(403, str(e)) from e
    if not path.startswith(f"photos/{garage_id}/"):
        raise HTTPException(403, "photo belongs to another garage")
    try:
        data, content_type = storage.download(path)
    except Exception as e:
        raise HTTPException(404, "photo not found") from e
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, max-age=600"})
