"""All settings come from environment variables. Nothing secret lives in code."""

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# GCP / Firebase
GCP_PROJECT = _env("GOOGLE_CLOUD_PROJECT")
GCS_BUCKET = _env("GCS_BUCKET")
# "memory" uses the in-memory fake (tests, local demo without GCP); "firestore" uses the real client
# (which also honours FIRESTORE_EMULATOR_HOST).
DB_BACKEND = _env("DB_BACKEND", "firestore")

# Gemini models (keep names out of code)
LIVE_MODEL = _env("LIVE_MODEL", "gemini-live-2.5-flash-native-audio")
TEXT_MODEL = _env("TEXT_MODEL", "gemini-2.5-flash")
VISION_MODEL = _env("VISION_MODEL", "gemini-2.5-flash")

# Agent voice. The Live API has no speaking-rate setting (only a voice name), so pace is an instruction.
# LIVE_VOICE: a prebuilt voice name (e.g. Kore, Charon, Aoede); empty = the model's default voice.
# VOICE_PACE: "slower" (default: a little slower than normal, short pauses around numbers) or "normal".
LIVE_VOICE = _env("LIVE_VOICE")
VOICE_PACE = _env("VOICE_PACE", "slower")

# Push-to-talk: a held turn reaches Gemini only if it has at least this much speech (see app/speech.py),
# so a short tap, silence or background noise can never become a command.
PTT_MIN_SPEECH_MS = int(_env("PTT_MIN_SPEECH_MS", "200"))
PTT_SPEECH_RMS = int(_env("PTT_SPEECH_RMS", "300"))  # PCM16 level a voiced 20 ms frame must exceed

# Vehicle manual lookup (C08): owner's manuals (PDF) are imported by the manuals-ingest job from MANUALS_SOURCE
# (production: the private photos bucket, prefix manuals/). Chunks are embedded with EMBED_MODEL into Firestore.
MANUALS_SOURCE = _env("MANUALS_SOURCE", f"gs://{GCS_BUCKET}/manuals/" if GCS_BUCKET else "manuals/pdf")
EMBED_MODEL = _env("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(_env("EMBED_DIM", "768"))  # output_dimensionality; the vector index must use the same size
EMBED_BATCH = int(_env("EMBED_BATCH", "1"))  # texts per embed call (gemini-embedding-001 on Vertex: 1)
# Each PDF page is read by TRANSCRIBE_MODEL (scanned pages and spec tables too); TRANSCRIBE_WORKERS pages at a time.
TRANSCRIBE_MODEL = _env("TRANSCRIBE_MODEL", "gemini-2.5-flash")
TRANSCRIBE_WORKERS = int(_env("TRANSCRIBE_WORKERS", "4"))
MANUAL_TOP_K = int(_env("MANUAL_TOP_K", "3"))
MANUAL_MIN_SCORE = float(_env("MANUAL_MIN_SCORE", "0.6"))  # cosine similarity; weaker matches are "not found"

# Customer links
LINK_SECRET = _env("LINK_SECRET")  # HMAC key for /j/:token links
LINK_TTL_HOURS = int(_env("LINK_TTL_HOURS", "72"))
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://localhost:5173")

# Garage defaults used when a garage config does not set them
DEFAULT_LOW_STOCK = int(_env("DEFAULT_LOW_STOCK", "1"))
APPROVAL_NUDGE_MINUTES = int(_env("APPROVAL_NUDGE_MINUTES", "30"))

# Cloud Scheduler calls POST /api/tasks/sweep with an OIDC token for this service account and audience
SCHEDULER_SA_EMAIL = _env("SCHEDULER_SA_EMAIL")
SCHEDULER_AUDIENCE = _env("SCHEDULER_AUDIENCE")

# Browser origins allowed to call the API directly (comma separated). Not needed when Firebase Hosting
# rewrites /api to Cloud Run (same origin).
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS").split(",") if o.strip()]

# Auth: set to "1" only for local demos to skip Firebase ID token checks
AUTH_DISABLED = _env("AUTH_DISABLED") == "1"
