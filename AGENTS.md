# GarageCopilot

Voice-first AI back office for small Indian garages. A mechanic talks through a headset; an agent opens job cards, checks stock, gets customer approval for extra work, and keeps the owner's dashboard and the customer's status page live. Google AI Builders Cup entry: all-Google stack (Gemini, ADK, Cloud Run, Firestore). Demo path frozen **Oct 14, 2026**, submission **Oct 18, 2026**.

## Start of every session

1. Read `tasks.md` first. It is the source of truth for what is done, in progress and blocked.
2. Continue the first unchecked task. Do not redo checked tasks unless `tasks.md` says they are broken.
3. After finishing each task: run the tests, tick it in `tasks.md` with a one-line note, commit, push.

## Reference material

- `diagrams/architecture.png`: the architecture to follow.
- `diagrams/job-workflow.png`: the demo job end to end (exact voice lines, tool names, Firestore docs). Use it as the acceptance test for the backend.
- `GarageCopilot — Solution Doc.md`: product pitch and scope. **Its Architecture section and its "Next.js vs React" question are outdated; this file wins.**

## Architecture decisions (final)

- **One stateless FastAPI service on Cloud Run.** No in-memory state that matters; session state lives in Firestore.
- **Voice path:** phone → our WebSocket gateway → Gemini Live. Tools run server-side. Direct-to-Gemini with ephemeral tokens is a future option, not now.
- **Agents (ADK):** one Live agent owns the conversation and calls the fast tools directly (`create_job`, `update_stage`, `check_stock`, `log_part_used`, `close_job`, `get_vehicle_history`). Slower work goes to three sub-agents: Quote (`draft_quote`, `describe_photo` with Gemini vision), Comms (`send_status_link`, `send_quote` in the customer's language), Inventory (low-stock watch, reorder suggestion to owner).
- **Layering:** agent → tools → service layer → Firestore. Tools are thin. The service layer is the only code that touches Firestore. It checks the tenant, writes the data, writes `audit_log`, then calls `notify()`.
- **Multi-tenancy:** everything under `garages/{garageId}/...` (config, mechanics, customers, jobs/{jobId}/stages, inventory, quotes, audit_log). `firestore.rules` restricts access by a `garage` custom auth claim. Seed **two** garages to prove isolation.
- **Idempotency:** every tool call carries `garage_id` and `request_id`; a repeated `request_id` is a no-op (voice retries must never double-decrement stock).
- **Auth:** Firebase Auth. Mechanics: owner-invited phone OTP, or name + PIN on a shared garage phone. Owner: phone OTP. Customer: signed, unguessable, expiring per-job link (read-only except Approve/Reject); no login.
- **Side effects:** all go through one `notify()` function. WhatsApp is simulated for the demo (write the message to Firestore and log it); swapping in Meta's WhatsApp Cloud API or Cloud Tasks later must only change `notify()`.
- **Photos:** Cloud Storage at `photos/{garageId}/{jobId}/`, served through short-lived signed URLs.
- **Quote rule:** quotes above the garage's `config.quote_limit` always pause for customer approval.
- **Frontend (later, not backend scope):** one React (Vite) PWA with routes `/mechanic`, `/owner`, `/j/:token` on Firebase Hosting, reading Firestore with realtime listeners and the offline cache.
- **Ops:** secrets in Secret Manager or env vars (never committed); deploy via Cloud Build.
- **Scale stance:** no scale numbers and no load testing. Keep the design rules above so scaling later is configuration, not a rewrite.

## Keep it simple

- Plain functions over classes. One module per area. No ORMs, no DI frameworks, no generic repositories, no abstractions "for later" beyond the ones listed above.
- Few dependencies: FastAPI, uvicorn, google-adk, google-genai, google-cloud-firestore, google-cloud-storage, firebase-admin, pytest. Ask in `tasks.md` before adding anything else.
- Model names, garage settings and URLs come from config/env, not code.
- Prefer code a new teammate can read in one sitting over clever code.
- Tests must run without GCP credentials: use the Firestore emulator or a small in-memory fake behind the service layer, and stub Gemini calls.
- Never commit secrets. Keep `.env.example` up to date.

## tasks.md format

Group tasks by tier. Each line: `- [ ] T## Short task` and, once done, `- [x] T## Short task — note`. The note says what was built and anything the team should know (shortcuts taken, stubs, open questions). Keep a **Blocked / needs a human** section at the top for anything that needs credentials, a decision or a manual step, and a **Last session** section with 2–3 lines on where work stopped and what to do next.
