# GarageCopilot backend

One stateless FastAPI service for Cloud Run: the voice gateway (Gemini Live through ADK), the owner REST API
and the customer's signed link. Firestore is the source of truth; every screen listens to it live.

```
agent (ADK) -> tools -> service layer -> Firestore
                         check tenant -> write data -> write audit_log -> notify()
```

## Layout

| Path | What |
| --- | --- |
| `app/config.py` | every setting, read from env |
| `app/db.py` | Firestore client, plus the in-memory fake used by tests |
| `app/services/` | the service layer, the only code that touches Firestore. `core.run()` does tenant check, idempotent `request_id`, audit log, notify |
| `app/notify.py` | the only exit for side effects (WhatsApp simulated: writes `garages/{g}/messages`) |
| `app/tools.py` | thin ADK tools for the Live agent and the Quote / Comms / Inventory sub-agents |
| `app/agent.py` | Live agent + sub-agents (called as `AgentTool`s) |
| `app/gateway.py` | `/ws/voice` WebSocket: phone audio <-> ADK `run_live` |
| `app/routes_*.py` | REST: owner, auth, customer link, photos, scheduler sweep |
| `app/links.py` | signed, expiring customer links |
| `app/storage.py`, `app/gemini.py` | Cloud Storage photos, non-live Gemini calls (vision captions, translation) |
| `app/seed.py` | two demo garages, 30 parts each |
| `app/manuals_ingest.py`, `app/services/manuals.py` | vehicle manual import (Cloud Run Job) and lookup (vector search) |
| `manuals/catalog.json`, `manuals/procedures/*.md` | which manual PDF is which vehicle; the team's procedure sheets |

## Run the tests

```
cd backend
uv sync
uv run pytest
```

No GCP credentials needed: Firestore is an in-memory fake and Gemini is stubbed. To run the same suite against
the real Firestore emulator (needs Node and Java), plus the `firestore.rules` tests, from the repo root:

```
npx firebase-tools@14 emulators:exec --only firestore --project demo-garage \
  "cd backend && TEST_AGAINST_EMULATOR=1 uv run pytest"
```

`tests/test_e2e_workflow.py` replays the demo job from `diagrams/job-workflow.png` step by step.

## Run locally

```
cp .env.example .env            # repo root; fill in what you have
cd backend
# Firestore emulator in another terminal: npx firebase-tools@14 emulators:start --only firestore --project demo-garage
FIRESTORE_EMULATOR_HOST=localhost:8080 GOOGLE_CLOUD_PROJECT=demo-garage uv run python -m app.seed
FIRESTORE_EMULATOR_HOST=localhost:8080 GOOGLE_CLOUD_PROJECT=demo-garage LINK_SECRET=dev AUTH_DISABLED=1 \
  uv run uvicorn app.main:app --reload
```

With `AUTH_DISABLED=1` (local only) the bearer token can be `dev:<garage>:<uid>:<role>`, e.g.
`curl -H "Authorization: Bearer dev:shree-auto:o-asha:owner" localhost:8000/api/owner/dashboard`.
Voice needs real Gemini credentials (`GOOGLE_GENAI_USE_VERTEXAI=TRUE` + project, or `GOOGLE_API_KEY`).

Agent voice settings: the Live API has no speaking-rate setting, only a voice name. `VOICE_PACE=slower` (default)
tells the agent to speak calmly and a little slower, pausing around numbers; `normal` removes that line.
`LIVE_VOICE` picks a prebuilt voice (e.g. `Kore`, `Charon`, `Aoede`); empty keeps the model default. Playback speed
in the browser is never changed (that would lower the pitch).

## API

| Endpoint | Who |
| --- | --- |
| `GET /health` | anyone |
| `WS /ws/voice?token=<ID token>[&ptt=1]` | mechanic or owner (the token's role picks the agent, see below). Binary 16 kHz PCM16 in, 24 kHz PCM16 out; JSON transcripts, tool results, `turn_complete`; `{"type":"text"}` typed fallback; `{"type":"start"/"stop"}` push-to-talk. Push-to-talk (`ptt=1`): the gateway holds each turn and sends it to Gemini on release only if it contains speech (`app/speech.py`: at least `PTT_MIN_SPEECH_MS` of 20 ms frames above `PTT_SPEECH_RMS` and 3x the turn's background); otherwise it replies `{"type":"ignored","reason":"no speech"}` and Gemini never sees the turn, so a tap, silence or noise can't trigger an action. One live connection per mechanic: opening another closes the older one with code 4409. Each audio chunk is forwarded once (an aggregate `partial=False` event repeating a streamed turn is skipped) |
| `POST /api/auth/pin` `{garage_id, name, pin}` | shared garage phone -> Firebase custom token |
| `POST /api/auth/claim` | after first phone-OTP sign-in: attaches the garage claim from the owner's invite |
| `GET /api/me`, `GET /api/jobs` (open jobs, compact) | owner or mechanic |
| `GET /api/owner/dashboard` (tiles + garage, jobs, reorder asks, recent messages), `/jobs`, `/jobs/{id}`, `/inventory`, `/audit` | owner |
| `POST /api/owner/inventory/{part}/restock`, `/reorder`, `/reorder-later`, `POST /api/owner/mechanics` | owner |
| `POST /api/jobs/{job}/photos` (raw image body) | owner or mechanic |
| `GET /api/j/{token}` | customer: status page data |
| `POST /api/j/{token}/quotes/{quote}/approve`, `/reject` | customer |
| `POST /api/j/{token}/session` | customer: custom token to listen live to their one job |
| `POST /api/tasks/sweep` | Cloud Scheduler (OIDC): approval nudges, low-stock reorder asks |

Writes from the API take an optional `request_id`; a repeated one returns the first result and changes nothing.

### Owner voice agent

An owner token on `/ws/voice` gets the owner agent (`agent.build_owner_agent`, on `LIVE_MODEL`) instead of the
mechanic's Live agent. Its tools (`tools.OWNER_TOOLS`) are thin wrappers over existing services: `today_summary`,
`list_open_jobs`, `job_details`, `pending_approvals`, `low_stock`, `recent_activity` (read-only), and
`answer_reorder` (yes / later on an open reorder ask, via `inventory.reorder` / `reorder_later`), the only write.
Owner tools refuse a mechanic session and the mechanic's tools refuse an owner session, on top of each agent only
having its own tools. Transcripts use role `owner`; headset notices are not spoken to the owner.

## Vehicle manuals (lookup for the voice agents)

Mechanics ask "spark plug gap for Activa?" or "how do I replace the clutch plates?"; the `lookup_manual` tool
finds the passages with Firestore vector search and the agent answers only from them, with the source
("Splendor Plus manual, page 58"), or says it isn't in the manual. Lookup, never diagnosis.

- **Data:** `manuals/{manual_id}` (title, make, models, kind owner|procedure, source, pages, ingested_at) and a flat
  `manual_chunks/{id}` (manual_id, title, models, kind, page, section, text, `embedding` vector). Global, not per
  garage; backend-only in `firestore.rules`. Lookups are audited in the garage's `audit_log` (`lookup_manual`).
- **Sources:** owner's manuals are PDFs in the private bucket, `gs://<GCS_BUCKET>/manuals/` (`MANUALS_SOURCE`); in
  development `backend/manuals/pdf/` (git-ignored). Manufacturer PDFs are copyrighted and never committed; only
  extracted text goes into Firestore. `manuals/catalog.json` maps each exact file name to title, make, models and
  kind; a PDF not listed there is skipped. Procedure sheets are `manuals/procedures/*.md` with front matter
  (`title`, `make`, `models: [..]`, `kind: procedure`) and are part of the image.
- **Import:** `python -m app.manuals_ingest [<folder or gs://bucket/prefix/>] [--force]` reads PDFs and the procedure
  sheets, chunks them (a chunk never spans a page; about 450 words, 40-word overlap, nearest
  heading kept as `section`), embeds them with `EMBED_MODEL` (`RETRIEVAL_DOCUMENT`, `EMBED_DIM` dims) and replaces
  that manual's chunks. Unchanged files (md5 in Cloud Storage, size + time locally) are skipped, so re-runs are
  cheap. It exits 1 if any file failed.
- **Reading PDF pages (C08b):** the PDF's own text is not enough: scanned manuals (the Swift) have none, and spec
  tables come out as all labels then all values, so a spec can't be matched to its number. So pypdf splits each PDF
  into one-page PDFs and `TRANSCRIBE_MODEL` (default `gemini-2.5-flash`) transcribes every page as plain text with
  table rows as `label: value unit` lines, numbers copied exactly, `EMPTY` for a blank page. `TRANSCRIBE_WORKERS`
  (default 4) pages are read at a time, so a 150-page manual takes minutes. A page Gemini fails on twice falls back
  to the PDF's own text for that page and is logged; the report line says how many pages fell back. Line breaks are
  kept in the stored chunks, so a row stays one line. Each page is still its own passage (exact page numbers), and
  an unchanged manual is skipped on re-runs, so it is transcribed only once.
- **Settings:** `MANUALS_SOURCE`, `TRANSCRIBE_MODEL`, `TRANSCRIBE_WORKERS`, `EMBED_MODEL` (default `gemini-embedding-001`), `EMBED_DIM` (768),
  `EMBED_BATCH` (texts per embed call, 1 for gemini-embedding-001 on Vertex AI), `MANUAL_TOP_K` (3),
  `MANUAL_MIN_SCORE` (0.6 cosine similarity: weaker matches count as "not in the manual").

### Add a manual (production, all on Google Cloud)

1. Add its exact file name to `manuals/catalog.json` (title, make, models, kind `owner`) and deploy (push to main).
2. Upload the PDF: `gcloud storage cp "<file>.pdf" gs://<GCS_BUCKET>/manuals/` (or drag it into the bucket's
   `manuals/` folder in the Cloud console).
3. Run the import: `gcloud run jobs execute manuals-ingest --region=asia-south1 --wait`
4. Read what it did: `gcloud run jobs executions list --job=manuals-ingest --region=asia-south1`, then
   `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="manuals-ingest"' --limit=50 --format='value(textPayload)'`
   (or Cloud console > Cloud Run > Jobs > manuals-ingest > Logs). One line per file: ingested / unchanged / skipped / failed.

The job is the backend image started with `python -m app.manuals_ingest` (deployed by `cloudbuild.yaml`, never run
by the deploy). The runtime service account needs read access to the bucket (it has Storage Object Admin for
photos) and Vertex AI User for the transcription and the embeddings.

### Vector index (once per project)

`firestore.indexes.json` has the composite vector index on `manual_chunks` (`models` array-contains + `embedding`,
flat, 768 dims; cosine is chosen at query time): `npx firebase-tools deploy --only firestore:indexes`. Or with gcloud:

```
gcloud firestore indexes composite create --collection-group=manual_chunks --query-scope=COLLECTION \
  --field-config=field-path=models,array-config=contains \
  --field-config=field-path=embedding,vector-config='{"dimension":"768","flat":"{}"}'
```

If `EMBED_DIM` changes, create a new index with that dimension and re-run the job with `--force`
(`gcloud run jobs execute manuals-ingest --region=asia-south1 --args=-m,app.manuals_ingest,--force --wait`).
The Firestore emulator runs these vector queries without an index (the test suite passes on it).

### Not done: import automatically when a PDF is uploaded

The stretch goal (start the job when a file lands in `manuals/`) is not built. Eventarc can't start a Cloud Run Job
directly; it would need an Eventarc trigger on the bucket's object-finalized events routed to a small Workflows
workflow that runs the job. Until then: upload, then run step 3. The demo does not depend on it.

## Deploy

`cloudbuild.yaml` (repo root) tests, builds `backend/Dockerfile`, pushes to Artifact Registry and deploys to
Cloud Run, then deploys the `manuals-ingest` Cloud Run Job from the same image (deploying does not run it).
Rules and indexes: `npx firebase-tools deploy --only firestore:rules,firestore:indexes`. One-off project setup is listed in
`tasks.md` under "Blocked / needs a human".
