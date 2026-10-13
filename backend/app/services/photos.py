"""Job photos: upload, list with signed URLs."""

import uuid

from app import config, db, gemini, storage
from app.services import core, jobs
from app.services.core import Invalid, get_doc

TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 8 * 1024 * 1024


def add_photo(who, garage_id, request_id, job_id, data: bytes, content_type: str):
    def work():
        if content_type not in TYPES:
            raise Invalid(f"photo must be one of {sorted(TYPES)}")
        if not data or len(data) > MAX_BYTES:
            raise Invalid("photo is empty or larger than 8 MB")
        get_doc(jobs.job_ref(garage_id, job_id))
        path = f"photos/{garage_id}/{job_id}/{uuid.uuid4().hex[:10]}.{TYPES[content_type]}"
        storage.upload(path, data, content_type)
        photo = {"path": path, "at": core.now(), "by": who["name"], "caption": ""}
        jobs.job_ref(garage_id, job_id).update({"photos": db.ArrayUnion([photo]), "last_photo": path})
        return {"job_id": job_id, "path": path}, []

    return core.run(who, garage_id, request_id, "add_photo", work)


def photo_url(garage_id: str, path: str) -> str:
    if not path.startswith(f"photos/{garage_id}/"):
        raise core.Forbidden("photo belongs to another garage")
    return storage.signed_url(path)


CAPTION_PROMPT = (
    "This photo was taken by a mechanic to show a customer a worn or damaged vehicle part. "
    "Reply with one short phrase (at most 6 words) describing only what is visible, "
    "e.g. 'friction surface glazed' or 'brake pad worn thin'. No diagnosis, no advice."
)


def describe_photo(who, garage_id, request_id, job_id, path: str = ""):
    """Caption the job's latest photo (or `path`) with Gemini vision; saved on the job."""
    def work():
        job = get_doc(jobs.job_ref(garage_id, job_id))
        photo = path or job.get("last_photo")
        if not photo:
            raise Invalid(f"no photo on {job_id} yet")
        if not photo.startswith(f"photos/{garage_id}/{job_id}/"):
            raise core.Forbidden("photo belongs to another job")
        data, mime = storage.download(photo)
        caption = gemini.generate(config.VISION_MODEL, CAPTION_PROMPT, image=data, mime_type=mime).strip(" .\"'")
        update = {f"photo_captions.{photo.rsplit('/', 1)[-1].split('.')[0]}": caption}
        if photo == job.get("last_photo"):
            update["last_photo_caption"] = caption
        jobs.job_ref(garage_id, job_id).update(update)
        return {"job_id": job_id, "path": photo, "caption": caption}, []

    return core.run(who, garage_id, request_id, "describe_photo", work)
