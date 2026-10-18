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

Reply language (C11): the first and strictest line of the mechanic and owner instructions (`app/language.py`
`rule()`) is "reply in the language of the person's latest turn" (English → English, Hindi → Hindi, Marathi →
Marathi, Hinglish → Hinglish; never switch because the customer, a tool result or earlier turns use another
language; names, plates, part names and numbers unchanged), with short examples. The voice screens have a picker:
Auto (default) / English / हिंदी / मराठी, remembered per device; a pinned language is sent as `/ws/voice?lang=hi`
and replaces the rule with "always answer in Hindi". It goes into `speech_config.language_code` (`hi-IN`, `mr-IN`,
`en-IN`) only with `LIVE_LANGUAGE_CODE=1`: Google's Live API docs say native-audio models choose the language
themselves and don't accept a language code (half-cascade models do), so the default is the instruction only.
Guardrail: in Auto mode the gateway compares each turn's input and output transcriptions by script (Devanagari vs
Latin; Hindi and Marathi can't be told apart this way). A clear mismatch logs `language mismatch` with both
snippets and adds a one-line `[system]` reminder to the session as partial content (Gemini doesn't reply to it).

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
| `GET /api/owner/settings`, `PUT /api/owner/settings` (`{"changes": {...}, "request_id"}`) | owner. Fields: `quote_limit` (auto-approve limit, whole rupees 0 to 1,00,000; 0 = always ask the customer), `name`, `city`, `lang` (default customer language), `supplier`, `reorder_qty` (1-999), `low_at` (0-999, low-stock level for parts without their own). `services/settings.py` validates, saves only what changed and audits it (`update_settings`, "changed the auto-approve limit from ₹500 to ₹0"). Bad values → 409 with the reason |
| `POST /api/jobs/{job}/photos` (raw image body) | owner or mechanic |
| `GET /api/j/{token}` | customer: status page data. Quotes carry `text_en` / `text_hi` and `messages` lists what the garage sent this customer for the job (`kind`, `at`, `text_en`, `text_hi`), for the page's English / हिंदी switch (C12). Texts are translated once when sent (`jobs.customer_texts`); WhatsApp (`text`) stays in the customer's own language |
| `POST /api/j/{token}/quotes/{quote}/approve`, `/reject` | customer |
| `POST /api/j/{token}/session` | customer: custom token to listen live to their one job |
| `POST /api/tasks/sweep` | Cloud Scheduler (OIDC): approval nudges, low-stock reorder asks |

Writes from the API take an optional `request_id`; a repeated one returns the first result and changes nothing.

### Owner records (C17)

Owner-only, tenant-checked reads over the data the garage already has, all in `services/reports.py` (aggregates are
computed on read for now; moving to stored daily totals later only changes that module). Dates are the garage's
local day; `from`/`to` filter on the check-in date.

| Endpoint | What |
|---|---|
| `GET /api/owner/jobs?from=&to=&status=open\|closed&mechanic=&q=&cursor=` | every job, newest first, 50 per page (`next_cursor`), each row: date, job, vehicle + plate, customer, mechanic, status, parts + consumables + labour = bill, cost, margin, time taken; `totals` for the whole filter (jobs, revenue, average bill, average time, cost, margin) |
| `GET /api/owner/jobs.csv?…` | the same filter as CSV |
| `GET /api/owner/jobs/{id}` | the job plus timeline (time per stage), money, quotes and decisions, messages sent, photos (signed URLs) |
| `POST /api/owner/jobs/{id}/status-link` | resend the customer's status link |
| `GET /api/owner/customers?q=`, `/customers/{id}` | name, phone, language, vehicles, visits, total spent, last visit, open jobs; detail adds their jobs |
| `GET /api/owner/vehicles?q=`, `/vehicles/{plate}` | every plate seen: model, owner, visits, last service and what was done, total spent; detail = full service history |
| `GET /api/owner/staff?period=today\|week\|month` | per mechanic: finished today / this week / this month, open now, average time, revenue, parts logged, last active, jobs finished per day |
| `POST /api/owner/mechanics/{uid}/deactivate` (and `/reactivate`) | a switched-off mechanic's PIN login and phone claim fail; their history stays |

No Firestore composite indexes are needed: the reads stream a garage's collections and filter in Python. The owner
agent gets `mechanic_jobs`, `revenue_for` and `vehicle_last_visit` for "how many jobs did Raju finish this week?",
"how much did we make this month?" and "when did MH12AB1234 last come in?".

### Model Armor screening (C18)

Google Cloud's Model Armor checks text for prompt injection and jailbreaks, malicious URLs, harmful content and
sensitive data. `app/armor.py`: `screen_prompt(text, where)` (sanitizeUserPrompt) and `screen_response(text, where)`
(sanitizeModelResponse) return `{ok, reasons}` and log every verdict; `ok` is `None` when Model Armor couldn't be
asked. Called over REST at the regional endpoint `https://modelarmor.<location>.rep.googleapis.com/v1/<template>:...`
with google-auth (already installed), on a small thread pool with a timeout. It is an extra layer next to the topic
guard and the web-search consent check, using the same `gateway.Guard` points; it changes neither.

| Where | When | Flagged | Model Armor down |
|---|---|---|---|
| Web-search results (`web_search_fixes`) | before the Live agent sees them | dropped: `found: false`, "results failed a safety check" | refused (fail closed) |
| A front-desk caller's finished words | in the background, alongside the reply | refused like an off-topic request; same strikes, so the 2nd flag ends the call; noted on the Calls list | turn goes on, logged |
| Typed text (all voice screens) | before it is sent, together with the topic check | never sent; the screen says "That can't be sent" | sent, logged |
| Every agent's reply | after the turn | logged and counted only (it was already spoken) | logged |

Each flag is an `armor_flagged` audit entry (owner's feed: "AI safety: flagged by Model Armor · where · filters · action").
**Limitation:** spoken audio goes straight to Gemini Live, so speech can only be screened once its transcription
arrives: the agent may already be answering, which is why a flagged caller turn is cut off and refused rather than
stopped before Gemini hears it, and why mechanic and owner speech isn't screened (their typed text is).
Settings: `MODEL_ARMOR_TEMPLATE` (full name; **empty = off**, no calls: tests and local dev), `MODEL_ARMOR_LOCATION`
(default: from the template name), `MODEL_ARMOR_TIMEOUT_SECONDS` (3), `MODEL_ARMOR_WORKERS` (8 calls at once per
instance; more go unchecked), `MODEL_ARMOR_MAX_CHARS` (4000). Setup: DEPLOY.md section 18.

### AI front desk: customers call the garage (C15)

A customer calls and the front desk agent (`agent.build_front_desk_agent`, on `LIVE_MODEL`, its own tools in
`tools.FRONT_DESK_TOOLS` over `services/frontdesk.py`) answers in the caller's language (the C11 rule).

- **Starting a call (web call for the demo):** `POST /api/j/{token}/call` from the customer's own status page
  ("Call the garage" button) gives a **verified** call: the number is the job's. `POST /api/call/start
  {garage_id, phone}` from the website (landing page) gives an **unverified** one (the number was typed). Both
  return a short-lived signed caller token (`call.…`, `CALL_TOKEN_MINUTES`) for `/ws/voice?token=…`; the gateway
  sees the `call.` prefix and runs the front desk agent with the phone and `verified` in session state (never from
  the model). Calls are rate-limited per number (`CALLS_PER_PHONE_HOUR`) and per garage (`CALLS_PER_GARAGE_HOUR`).
- **What it can do:** `my_vehicle_status` (only for a verified caller and only their own jobs; an unverified
  caller hears that details can't be shared on this line), `send_status_link_again` / `send_quote_again` (always to
  the customer's number on file, never to the caller, so a stranger learns nothing), `request_estimate` (a rough
  estimate from stock prices goes to the **owner** first; the caller gets it on WhatsApp only after the owner taps
  Send), `book_dropoff` (`bookings`), `request_callback` ("Call back Ramesh about the bill"; there is no live
  transfer). No staff tool runs for a caller session (`tools._who` refuses the `caller` role).
- **Owner:** `GET /api/owner/calls` (recent calls with the caller's first words as the summary and what the AI
  did, open callbacks, estimates to confirm, drop-offs), `POST /api/owner/estimates/{id}/send` (optional corrected
  `total`) or `/drop`, `POST /api/owner/callbacks/{id}/done`. The Today tab has a Calls card. `calls`, `callbacks`,
  `estimates` and `bookings` hold phone numbers: owner-only in `firestore.rules`.

#### Real phone line (later, not built)

The gateway already speaks 16 kHz PCM in, 24 kHz PCM out over a WebSocket, so a phone number is a bridge, not a
new backend. With a telephony provider that streams call audio over WebSockets (e.g. Twilio Media Streams, or
Exotel's voice streaming in India):

1. Buy a number and point its incoming-call webhook at a small new endpoint (e.g. `POST /api/phone/incoming`) that
   answers with the provider's "connect a media stream" instruction to `wss://<service>/ws/phone`.
2. `/ws/phone`: read the provider's start message (caller ID = `From`), look up the garage by the dialled number,
   create the call with `frontdesk.start_call(garage, from, verified=<caller ID matches a job's phone>, via="phone")`,
   then run the same `live_events` / `downstream` loop as `/ws/voice` with the front desk agent.
3. Audio conversion: phone audio is 8 kHz G.711 μ-law, base64 in JSON frames. In: μ-law → 16-bit PCM → resample
   8 kHz → 16 kHz → Gemini. Out: Gemini's 24 kHz PCM → resample to 8 kHz → μ-law → base64 frames back. Python's
   `audioop` was removed in 3.13, so this needs a few lines of numpy-free code (a 256-entry μ-law table and simple
   linear resampling) or the provider's own PCM option if it has one.
4. Hands-free only (no push-to-talk on a phone): use the hands-free path (automatic activity detection) and
   the echo guard the browser client has (don't forward caller audio while the agent is speaking).
5. Caller ID is spoofable: keep "verified" for numbers that match the job's phone, but still never read out a
   bill or details to an unverified line beyond what the web call allows.

### Manual first, then a web search with the mechanic's OK (C14)

For a specific problem or spec the mechanic first gets `lookup_manual`. If the manual has nothing, the agent says
so and asks "Shall I search online for known causes and fixes?", and does nothing until the mechanic says yes.
Then it calls `web_search_fixes(question, vehicle, confirmed=true)`; the tool refuses unless `confirmed` is exactly
true. It runs a small ADK sub-agent (`agent.build_web_search_agent`, on `WEB_SEARCH_MODEL`, default `TEXT_MODEL`)
whose only tool is ADK's built-in `google_search` (Gemini grounding with Google Search; built-in tools can't share an
agent with function tools, and ADK's own docs advise against running the search agent on the Live model), via
`services/websearch.py`. The answer is 2-3 "cause: known fix" points plus the source site names from the grounding
metadata; the agent says they are from the web, not the manual, one at a time, never as a diagnosis; anything about
brakes, fuel leaks or electrical / EV high-voltage parts ends with "Check against the workshop manual". The search
is audited (`web_search_fixes`, feed: "searched the web") and the transcript chip shows "Web · <sites>". Google's
grounding terms ask apps to display the returned search suggestions: their HTML is kept in
`garages/{g}/web_searches/{request_id}` (see Blocked).

### Consumables (C13)

An inventory item can list the consumables used each time it is fitted: `with: [{part_id, qty}]` (e.g. the
Splendor clutch plate set uses a cover gasket, 4 M6 bolts, 4 washers and grease). Consumables are normal inventory
items with `kind: "consumable"`, `price`, `cost` (what the garage paid) and `billable` (charged to the customer, or
the garage's own cost); every item has a `cost`. `log_part_used` takes the part and its consumables (qty × parts
fitted) out of stock in one idempotent call: billable ones become their own bill lines (`consumable: true`), the
others go on the job as `consumables` with their cost. A consumable short in stock never blocks the main part: what
is there is used, the shortfall is in the result and the item is flagged low. The result's `say` is what the agent
reads back ("Logged 1 Clutch plate set and the usual fittings."). `draft_quote` adds billable consumables as lines.
`jobs.money(job)` = parts + consumables + labour = bill, `cost` of parts and consumables used, `margin`; it is on
every dashboard job card (`money`) and in `job_details` for the owner agent; the dashboard adds `cost_today` and
`margin_today`. In the seed, the clutch job's fittings are the garage's own cost (so the demo quote stays ₹950);
brake, chain and oil-change jobs carry billable consumables.

### Auto-approve limit (owner Settings, C09)

Quotes at or below the garage's `quote_limit` are approved without asking the customer. `send_quote` reads the
**current** setting when the quote is sent (not a copy from when the job or draft was made), so an owner's change
applies to the next quote at once. An auto-approved quote is stored with `auto: true` and the limit used; the tool
result carries `say: "Approved automatically: within the ₹X limit"` for the mechanic, the customer page shows
"Approved automatically", and the activity feed says so.

### Owner voice agent

An owner token on `/ws/voice` gets the owner agent (`agent.build_owner_agent`, on `LIVE_MODEL`) instead of the
mechanic's Live agent. Its tools (`tools.OWNER_TOOLS`) are thin wrappers over existing services: `today_summary`,
`list_open_jobs`, `job_details`, `pending_approvals`, `low_stock`, `recent_activity`, `garage_settings` (read-only), and
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
