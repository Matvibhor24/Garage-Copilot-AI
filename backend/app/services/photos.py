"""Job photos: upload, list with signed URLs."""

import logging
import uuid

from app import config, db, gemini, storage
from app.services import core, jobs
from app.services.core import Invalid, get_doc

log = logging.getLogger(__name__)

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
        try:
            storage.upload(path, data, content_type)
        except Exception as e:  # a missing bucket or permission: say so instead of a bare 500
            log.exception("photo upload to Cloud Storage failed")
            raise Invalid("couldn't save the photo: photo storage isn't set up right "
                          "(owner: Settings → Check photo storage)") from e
        photo = {"path": path, "at": core.now(), "by": who["name"], "caption": ""}
        jobs.job_ref(garage_id, job_id).update({"photos": db.ArrayUnion([photo]), "last_photo": path})
        return {"job_id": job_id, "path": path}, []

    return core.run(who, garage_id, request_id, "add_photo", work)


def photo_url(garage_id: str, path: str) -> str:
    """A URL the browser can load: a Cloud Storage signed URL, or, if signing fails (missing IAM permission), a
    short-lived link served by the backend (/api/photos/{token}). Never raises because of signing (C21)."""
    if not path.startswith(f"photos/{garage_id}/"):
        raise core.Forbidden("photo belongs to another garage")
    try:
        return storage.signed_url(path)
    except Exception:
        log.exception("signing a photo URL failed; serving it through the backend instead (see the owner's storage check)")
        from app import links

        return f"/api/photos/{links.make_photo_token(garage_id, path)}"


# What each storage step needs when it fails (the owner's "Check photo storage" button, C21)
STORAGE_HINTS = {
    "bucket": "Set the bucket name: GCS_BUCKET (Cloud Build substitution _GCS_BUCKET) must match your bucket.",
    "write": "Give the backend's service account the Storage Object Admin role on the bucket.",
    "read": "Give the backend's service account the Storage Object Admin role on the bucket.",
    "sign": "Give the backend's service account 'Service Account Token Creator' on itself and enable "
            "iamcredentials.googleapis.com. Until then photos are served through the backend instead.",
    "delete": "Give the backend's service account the Storage Object Admin role on the bucket.",
}


def storage_check(who, garage_id) -> dict:
    """Try each step photos need, in order, and say which fails and how to fix it. Owner only."""
    core.check_tenant(who, garage_id)
    if who.get("role") != "owner":
        raise core.Forbidden("owner only")
    steps = []

    def step(key, label, fn):
        try:
            detail = fn() or "OK"
            steps.append({"step": key, "label": label, "ok": True, "detail": detail})
            return True
        except Exception as e:  # report the exact problem, then stop: later steps depend on this one
            hint = STORAGE_HINTS[key]
            if "does not exist" in str(e) or "404" in str(e):  # a wrong bucket name, not a permission
                hint = (f"No bucket named '{config.GCS_BUCKET}' exists in this project. " + STORAGE_HINTS["bucket"]
                        + " (Locally: fix GCS_BUCKET, run `source` again, restart the backend.)")
            steps.append({"step": key, "label": label, "ok": False, "detail": str(e)[:300], "hint": hint})
            return False

    def bucket():
        if storage.is_fake():
            return "in memory (tests / local demo)"
        if not config.GCS_BUCKET:
            raise ValueError("GCS_BUCKET is empty")
        return config.GCS_BUCKET

    path = f"photos/{garage_id}/_check/{uuid.uuid4().hex[:8]}.txt"
    body = b"GarageCopilot storage check"

    def read_back():
        if storage.download(path)[0] != body:
            raise ValueError("the file read back is different")

    def sign():
        storage.signed_url(path)

    if step("bucket", "Bucket name", bucket) and step("write", "Save a test file",
                                                      lambda: storage.upload(path, body, "text/plain")):
        if step("read", "Read it back", read_back):
            step("sign", "Make a signed link", sign)
        step("delete", "Delete the test file", lambda: storage.delete(path))
    return {"bucket": config.GCS_BUCKET, "ok": all(s["ok"] for s in steps), "steps": steps}


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
