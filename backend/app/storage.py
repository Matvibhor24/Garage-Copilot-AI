"""Cloud Storage for job photos: photos/{garageId}/{jobId}/..., served by short-lived signed URLs; and the
owner's manuals the manuals-ingest job reads from manuals/. In tests (or DB_BACKEND=memory) an in-memory fake
is used (one namespace, the bucket name is ignored)."""

from datetime import timedelta

from app import config

_fake = None  # dict path -> (bytes, content_type) when faked


def use_fake() -> dict:
    global _fake
    _fake = {}
    return _fake


def is_fake() -> bool:
    """True in tests and in DB_BACKEND=memory: files live in memory, no bucket needed."""
    return _fake is not None or config.DB_BACKEND == "memory"


def _bucket(name: str = ""):
    from google.cloud import storage

    return storage.Client(project=config.GCP_PROJECT or None).bucket(name or config.GCS_BUCKET)


def list_files(prefix: str, bucket: str = "") -> list[dict]:
    """Files under a prefix: [{path, size, md5}] (md5 changes when the file does)."""
    if _fake is not None:
        import hashlib

        return [{"path": p, "size": len(d), "md5": hashlib.md5(d).hexdigest()}
                for p, (d, _) in sorted(_fake.items()) if p.startswith(prefix)]
    return [{"path": b.name, "size": b.size, "md5": b.md5_hash}
            for b in _bucket(bucket).list_blobs(prefix=prefix) if not b.name.endswith("/")]


def read(path: str, bucket: str = "") -> bytes:
    if _fake is not None:
        return _fake[path][0]
    return _bucket(bucket).blob(path).download_as_bytes()


def upload(path: str, data: bytes, content_type: str) -> None:
    if _fake is not None or config.DB_BACKEND == "memory":
        (_fake if _fake is not None else use_fake())[path] = (data, content_type)
        return
    _bucket().blob(path).upload_from_string(data, content_type=content_type)


def download(path: str) -> tuple[bytes, str]:
    if _fake is not None:
        return _fake[path]
    blob = _bucket().blob(path)
    data = blob.download_as_bytes()
    return data, blob.content_type or "image/jpeg"


def signed_url(path: str, minutes: int = 15) -> str:
    """A V4 signed GET URL. Raises if signing isn't possible; callers fall back (services/photos.photo_url)."""
    if _fake is not None or config.DB_BACKEND == "memory":
        return f"memory://{path}?expires={minutes}m"
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds, _ = google.auth.default()
    blob = _bucket().blob(path)
    expiration = timedelta(minutes=minutes)
    if isinstance(creds, service_account.Credentials):  # a key file (local dev): sign with its private key
        return blob.generate_signed_url(version="v4", expiration=expiration, method="GET", credentials=creds)
    # On Cloud Run there is no private key: sign through IAM (needs Service Account Token Creator on itself and
    # the IAM Credentials API).
    creds.refresh(Request())
    return blob.generate_signed_url(
        version="v4", expiration=expiration, method="GET",
        service_account_email=getattr(creds, "service_account_email", None), access_token=creds.token)


def delete(path: str) -> None:
    if _fake is not None:
        _fake.pop(path, None)
        return
    _bucket().blob(path).delete()
