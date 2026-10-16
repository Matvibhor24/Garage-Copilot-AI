import os

import pytest

from app import config, db, storage

# Set TEST_AGAINST_EMULATOR=1 (with FIRESTORE_EMULATOR_HOST) to run every service test
# against the real Firestore emulator instead of the in-memory fake.
EMULATOR = os.environ.get("TEST_AGAINST_EMULATOR") == "1" and os.environ.get("FIRESTORE_EMULATOR_HOST")


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setattr(config, "LINK_SECRET", "test-secret")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://gc.app")
    monkeypatch.setattr(config, "TOPIC_GUARD", False)
    from app import consent

    consent.reset()  # no real Gemini calls; tests/test_topic_guard.py turns it on
    storage.use_fake()


@pytest.fixture
def fake_db():
    if not EMULATOR:
        return db.use_fake()
    import httpx
    from google.cloud import firestore

    project = os.environ.get("GCLOUD_PROJECT", "demo-garage")
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    httpx.delete(f"http://{host}/emulator/v1/projects/{project}/databases/(default)/documents").raise_for_status()
    db._client = firestore.Client(project=project)
    return db._client


@pytest.fixture(autouse=True)
def no_real_gemini(monkeypatch):
    """Gemini is never called in tests. Translation returns '[lang] text' so tests can see it ran."""
    from app import gemini

    def fake_generate(model, prompt, image=None, mime_type=""):
        if mime_type == "application/pdf":  # manual page transcription: the page's own PDF text
            return fake_transcribe(image)
        if image is not None:
            return "part looks worn"
        lang = next(name for name in gemini.LANGUAGES.values() if f"into {name}." in prompt)
        return f"[{lang}] " + prompt.split("\n\n", 1)[1]

    monkeypatch.setattr(gemini, "generate", fake_generate)
    monkeypatch.setattr(gemini, "embed", fake_embed)


def fake_transcribe(page_pdf):
    import io

    from pypdf import PdfReader

    return PdfReader(io.BytesIO(page_pdf)).pages[0].extract_text() or "EMPTY"


STOP = {"the", "a", "an", "is", "of", "for", "on", "at", "to", "and", "in", "this", "what", "whats", "how", "do",
        "i", "should", "be", "it", "my", "with", "when", "every", "here", "you"}


def fake_embed(texts, task_type):
    """Deterministic bag-of-words vectors (512 buckets) instead of Gemini embeddings: shared words = similar."""
    import re
    import zlib

    out = []
    for text in texts:
        vector = [0.0] * 512
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if word not in STOP:
                vector[zlib.crc32(word.encode()) % 512] += 1.0
        out.append(vector)
    return out
