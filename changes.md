# Changes requested after the first local run (Oct 11, 2026) and the first Google Cloud deploy (Oct 15, 2026)

## Where things stand (read first)

- **Done and merged into `main`:** backend T01–T27, frontend F01–F10, the 3D vehicle view (F11), the owner's 3D
  garage floor (F12, `frontend/src/garage3d/`), and C01–C08b below (manual lookup merged Oct 13). See `tasks.md`.
- The team deployed to Google Cloud (Cloud Run + Firebase Hosting) and found the issues **C09–C17** (bottom of this
  file). **Do C09–C17 only, in that order** (C10 is a bug; the rest are features). Each one is its own commit.
- The 3D views live in `frontend/src/vehicle3d/` and `frontend/src/garage3d/`. Keep them working; update them where a
  change below says so (e.g. the stage order in C10).
- Deadline: submission **Oct 18, 2026**. If you run out of time, finish and push the completed tasks; never leave
  `main`-bound work half-done in one commit.

Found by the team running the app locally with the real backend, the Firestore emulator and real Gemini (Vertex AI).
Work these as tasks **C01–C16** (C01–C08b done): add them to `tasks.md` (new section "Changes after first local run"), then follow
the usual loop from `AGENTS.md` (one task per commit, tests, tick with a note, push). Keep the code simple.

Important: several of these only show up with the **real** backend and Gemini, not in demo mode. Don't mark a task
done just because demo mode looks right. Where you can't verify without a human (real voice), say exactly what you
changed and what the team should check, in the tick note and under "Blocked / needs a human".

---

## C01: Make every screen work well on laptops and desktops, not only phones

**Problem:** the app was built phone-first and looks like a narrow phone column on Windows/Mac laptops and desktops.
It must work well on any device.

**Where to look:** `frontend/src/styles.css`. `.page-narrow` (max-width 520px) is used by Home and the customer page,
and `.voice` (max-width 640px) by the mechanic screen. The owner screen already has some wide layouts
(`.tiles`, `.owner-grid`); check it too.

**Do:**
- Home: use the width on large screens (e.g. role cards side by side).
- Customer page (`/j/:token`): two columns on wide screens, e.g. the 3D vehicle and status on one side and the
  quote, timeline and bill on the other. The 3D view should get more room on desktop.
- Mechanic screen: on wide screens, transcript in the middle plus a side panel for the current job and the open
  jobs list; the orb and controls stay easy to reach.
- Owner: check tiles, jobs board, feed and stock at laptop sizes; no wasted space and no horizontal scroll.
  Job cards stay clickable (they open the 3D job viewer), and the viewer works at every size.
- Keep phones exactly as good as now (phone-first CSS with `min-width` media queries added on top).
- Mouse and keyboard should work everywhere: hover states, visible focus, space bar push-to-talk already exists.

**Done when:** no horizontal scroll and a deliberate layout at 375, 768, 1280 and 1920 px wide. Add a desktop
viewport (e.g. 1440×900) to the Playwright config alongside Pixel 7 and attach screenshots of all three screens at both sizes.

---

## C02: The voice agent sometimes says the same reply twice or three times

**Problem:** with real Gemini, the mechanic sometimes hears the agent's reply 2–3 times. Not every turn.

**Likely causes, check in this order:**
1. **Two live sessions at once.** `frontend/src/main.jsx` wraps the app in `<StrictMode>`, which runs effects twice
   in development. If the voice WebSocket gets opened twice (or not closed on remount, on the hands-free/push-to-talk
   switch in `Mechanic.jsx` `switchMode`, or with two mechanic tabs open), two Gemini sessions hear the same mic and
   both answer. The backend log prints "voice session closed for …" per connection; count open sessions. Make sure
   there is never more than one live connection per screen (guard in `useVoice` / `voice/client.js` `connect()`),
   and that closing really stops the mic and playback.
2. **Audio forwarded twice by the gateway.** `backend/app/gateway.py` `downstream()` forwards audio from every ADK event
   with `inline_data`. Check whether ADK `run_live` also emits a final/aggregated event that repeats audio already
   sent in partial events (look at `event.partial` and `turn_complete`). Forward each audio chunk once.
3. **The model repeats itself after tool results or `[notice]` messages.** Tighten the instruction in
   `backend/app/agent.py` (say the result once; after a tool call, don't restate what was already said).

**Done when:** a test proves the gateway never forwards the same audio twice for one turn (scripted ADK events
including a partial + final pair), the frontend can't open a second socket for the same screen, and the tick note
explains the root cause found. Real-voice check goes to "Blocked / needs a human".

---

## C03: The agent's voice is a little too fast; slow it down slightly

**Problem:** the spoken replies are slightly too fast for a mechanic in a noisy garage. Needs a small slowdown, not a big one.

**Do:**
- Check the current ADK / Gemini Live docs for a speaking-rate or speech setting on the Live model. If one exists,
  use it and put the value in config (env var, e.g. `VOICE_SPEED`), not in code.
- If there is no such setting, add a clear instruction in `backend/app/agent.py`: speak calmly and a little slower
  than normal, with short pauses between numbers. Also allow choosing the voice via config (`speech_config` with a
  prebuilt voice name, e.g. `LIVE_VOICE`), since some voices are naturally slower.
- **Don't** slow playback in the browser (changing the playback rate also lowers the pitch).

**Done when:** speed/voice are settings, documented in `.env.example` and `backend/README.md`. Real-voice check
goes to "Blocked / needs a human".

---

## C04: Voice agent for the owner

**Problem/feature:** the owner should be able to tap a button on their dashboard and talk to an agent about the
garage's operations ("How many bikes are in today?", "What's pending approval?", "How much did we make today?",
"Which parts are low?", "How long did Ramesh's job take?").

**Design (follow the existing architecture):**
- Reuse the `/ws/voice` gateway and the same audio protocol. The gateway already knows the caller's role from the
  token: for `role == owner`, build an **owner agent** instead of the mechanic's Live agent.
- New owner agent in `backend/app/agent.py` with its own short instruction (answers in one or two sentences, in
  the owner's language, numbers spoken clearly, never makes things up: every number comes from a tool).
- Owner tools in `backend/app/tools.py`, thin wrappers over **existing** service functions where possible
  (`owner.dashboard`, `jobs.list_jobs`, `jobs.get_job`, `inventory.list_inventory`, `owner.audit_log`):
  today's summary, open jobs (by stage / mechanic), one job's details, pending approvals, low stock, recent activity.
- Actions the owner may take by voice: answer an open reorder ask (Yes / Later) through the existing
  `inventory.reorder` / `inventory.reorder_later`. Nothing else writes. The owner agent must not use the mechanic's
  job tools (no creating jobs or logging parts).
- Frontend: a mic button on `/owner` that opens a voice panel (transcript + orb), reusing `src/voice/client.js` and
  the mechanic screen's pieces where possible. Works on phone and desktop (see C01). Add a demo-mode script for it too.
  The voice panel must not cover or break the 3D job viewer pop-up.

**Done when:** owner tools have unit tests (fake DB, Gemini stubbed), the gateway picks the right agent by role (test),
a mechanic token can't reach owner tools and vice versa, and the README documents it.

---

## C05: Customer page: the Approve / Decline card doesn't go away after choosing

**Problem:** on `/j/:token`, after the customer taps Approve or Decline, the quote's approval card (or its
"Approved / Declined" confirmation) stays on screen instead of disappearing. Seen with the real backend in local dev
mode (no Firebase config, so the page polls every 4 s), not in demo mode.

**Where to look:** `frontend/src/screens/Customer.jsx` `QuoteCard`. After the POST it shows a result card, then calls
`onDone` (the page's `reload`) after 1.6 s; the card should vanish because the quote is no longer `pending`. Find out
why it doesn't (stale data, reload not refetching, a second pending quote, the request failing silently, the
`useLiveView` change check in `src/data/live.js`, etc.).

**Do:** after a decision, show the confirmation briefly, then remove the card and show the quote under the decided
list ("Approved" / "Declined" chip). It must also be right after a page refresh and for a second customer tab. A
double tap must not cause an error toast.

**Done when:** reproduced first (note the root cause in the tick), fixed, and covered by a test against the real
backend shapes (not only the demo backend), plus the Playwright demo run still passing.

---

## C06: Push-to-talk must not trigger random actions when no useful speech was given

**Problem:** in push-to-talk mode, if the mechanic taps/holds the orb only very briefly (for example around one second) and does not clearly say anything, the agent can still interpret the turn as a command and move the current job to a random stage or perform another action.

This is dangerous because silence, mic noise, a clipped word, or an accidental tap must never cause a write action such as changing job stage, logging a part, creating a quote, or closing a job.

**Where to look:**
- `frontend/src/screens/Mechanic.jsx` push-to-talk start/stop handling.
- `frontend/src/voice/` mic capture / audio chunk sending.
- `backend/app/gateway.py` handling of `start` / `stop`, turn boundaries and audio sent to ADK/Gemini.
- `backend/app/agent.py` instructions around tool calls when the user intent is unclear.

**Do:**
- Reproduce with very short push-to-talk taps:
  - tap for ~0.2–0.5 s with silence;
  - hold for ~1 s with silence;
  - hold briefly with only background noise;
  - start speaking but release before a meaningful phrase is completed.
- Confirm whether Gemini receives a turn and whether it produces a transcript / tool call.
- Do not allow an empty, near-empty or clearly unusable push-to-talk turn to result in a state-changing tool call.
- Add a guard at the most reliable layer found during investigation. Prefer preventing an invalid turn from reaching the agent where possible rather than trying to undo a bad action afterward.
- For ambiguous or incomplete speech, the agent should ask for clarification instead of guessing an action.
- Keep normal short commands working, e.g. `"washing"`, `"start service"`, `"used one clutch plate"`.
- Do not break hands-free mode while fixing push-to-talk.

**Safety rule:** no state-changing operation should happen from silence, accidental taps, background noise, or low-confidence / incomplete intent.

**Done when:**
- Repeated short silent taps never change job state or invoke a write tool.
- Background noise alone never causes a write.
- A clipped / ambiguous utterance asks for clarification instead of guessing.
- Valid short commands still work.
- Add tests around the discovered root cause where practical (frontend PTT handling and/or gateway/agent behavior).
- Real-microphone verification is noted under "Blocked / needs a human" if it cannot be fully automated.

---

## C07: Browser Back/Forward navigation can bypass mechanic sign-in

**Problem:** after signing in as mechanic Raju, if the user presses the browser Back button to leave the mechanic screen and then presses Forward, the app returns directly to the mechanic screen without requiring sign-in again.

This means browser history can restore an authenticated mechanic view even though the user intentionally navigated away, which is unsafe on shared garage devices.

**Where to look:**
- `frontend/src/screens/Mechanic.jsx` mechanic sign-in / shift state.
- `frontend/src/App.jsx` route handling.
- Any local/session storage used for mechanic identity or active shift.
- Browser history / bfcache behavior when returning with Back/Forward navigation.

**Do:**
- Reproduce:
  - sign in as Raju;
  - reach the mechanic screen;
  - press browser Back;
  - then browser Forward;
  - confirm whether the mechanic screen is restored without authentication.
- Decide the intended session behavior explicitly:
  - browser navigation alone should not silently restore a privileged mechanic screen after leaving it;
  - require a fresh mechanic session check before showing the working screen.
- Make sure the fix handles browser back-forward cache (`pageshow` / persisted pages) if that is the cause.
- Do not break normal refresh behavior for an intentionally active signed-in shift unless the product decision says refresh should also sign out.
- Test sign-out separately: after sign-out, Back/Forward must never restore the mechanic session.

**Security rule:** browser history must not be usable to bypass mechanic authentication or restore a signed-out mechanic session.

**Done when:**
- Back then Forward does not expose the mechanic screen without a valid active mechanic session.
- After explicit sign-out, Back/Forward never restores the authenticated screen.
- Normal login still works.
- Refresh behavior matches the chosen session policy.
- Add a Playwright test for Back/Forward navigation and sign-out history behavior.

---

## C08: Vehicle manual lookup (RAG with Firestore vector search + Gemini embeddings)

**Why:** today the agent keeps records (jobs, stock, quotes) but can't help with the work itself. Mechanics should be
able to ask things like *"What should the Splendor's battery voltage be?"*, *"Spark plug gap for Activa?"*, *"Engine
oil grade and quantity?"* or *"How do I replace the clutch plates?"* and get a short spoken answer **from the
vehicle's manual, with the source**. This is the "light vehicle Q&A, grounded answers" stretch item from the solution
doc. It's **manual lookup, not diagnosis**: the agent quotes specs and steps; it never decides what is wrong with a vehicle.

**Decision (team): Firestore vector search + Gemini embeddings.** No Vertex AI RAG Engine, no other new service.

### Data

- **Sources** (the team provides them; don't download or invent manuals yourself):
  - **Owner's manuals (PDF)** for the seeded vehicles: Splendor Plus, Activa 6G, Pulsar 150, Swift (the car, for
    Ganesh Motors). Specs: battery, spark plug, tyre pressure, oil grade and capacity, clutch free play, service intervals.
  - **Procedure sheets (Markdown) the team writes**: e.g. clutch plate replacement (Splendor), chain adjustment,
    spark plug check, Activa drive belt inspection. Keep them in the repo at `backend/manuals/procedures/*.md` with
    front matter: `title`, `models` (list), `kind: procedure`. If you draft any of them, **put no numeric specs in a
    procedure sheet unless they come from an owner's manual**, start each with "Team-written general steps, check
    against the workshop manual", and list them under "Blocked / needs a human" for the team to review.
- **Copyright:** manufacturer PDFs **must not be committed** (the repo becomes public). Only the extracted text chunks go
  into Firestore.
- **Where the PDFs live (the product must run fully on Google Cloud):**
  - **Production: a private Cloud Storage folder**, `gs://<GCS_BUCKET>/manuals/` (the same private bucket as the photos,
    its own prefix; setting `MANUALS_SOURCE`, default `gs://<GCS_BUCKET>/manuals/`). Adding a manual = uploading the PDF there
    and running the ingest job (below). No laptop involved.
  - **Development only:** a local folder, `backend/manuals/pdf/` (already in `.gitignore`).
  - The team already has the four PDFs locally, with these exact file names (note the spaces, apostrophes and spellings):
    `Hero-Splendour-Plus-owner's-manual.pdf`, `Honda-activa-6g-owner's manual.pdf`, `Bajaj-pulsar-owner's-manul.pdf`,
    `maruti-swift-owner's-manual.pdf`. Don't rely on guessing models from file names: add a small committed catalog,
    `backend/manuals/catalog.json`, mapping each file name to `title`, `make`, `models` and `kind`, and fill it in for these
    four (Splendor Plus, Activa 6G, Pulsar 150, Swift). A PDF missing from the catalog is skipped with a clear message.
- **Firestore layout** (global, not per garage; manuals are the same for every garage):
  - `manuals/{manual_id}`: `title`, `make`, `models` (e.g. `["Splendor", "Splendor Plus"]`), `kind`
    (`owner` | `procedure`), `source` (file name), `pages`, `ingested_at`.
  - `manual_chunks/{id}`: `manual_id`, `title`, `models`, `kind`, `page`, `section`, `text`, `embedding` (Firestore
    `Vector`). A flat collection so one vector query can pre-filter by model.
  - `firestore.rules`: backend-only (no client reads). Add an explicit comment like the ones for `requests` and `phone_index`.

### Ingestion

- New script `python -m app.manuals_ingest [<folder or gs:// prefix>]` (default: `MANUALS_SOURCE`; idempotent: re-running
  replaces a manual's chunks; a manual whose file hasn't changed since the last run (size + updated time, or md5 from
  Cloud Storage) is skipped, so re-runs are cheap). Reading `gs://` uses `google-cloud-storage` (already a dependency).
  - PDF text per page with **`pypdf`** (the team approves this one new backend dependency). Markdown read directly.
  - Chunk by page/section, about 300–600 words with a small overlap. Keep `page` and the nearest heading as `section`.
  - Embed with the Gemini embedding model through `google-genai` (`client.models.embed_content`), task type
    `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for questions. Model name and size come from config:
    `EMBED_MODEL` (check the current docs for the right ID, e.g. `gemini-embedding-001`) and `EMBED_DIM` (e.g. 768,
    via `output_dimensionality`). Embed in batches.
  - Map a manual to models from its file name or front matter (e.g. `hero-splendor-plus-owners.pdf` → Splendor Plus).
- **Runs in the cloud as a Cloud Run Job** named `manuals-ingest`: the same backend image, started with
  `python -m app.manuals_ingest` instead of the web server, so it runs once and stops (costs nothing while idle).
  - Add it to `cloudbuild.yaml`: after the service deploy, `gcloud run jobs deploy manuals-ingest` with the image just
    built, the same runtime service account, env vars and region (`--command python --args -m,app.manuals_ingest`,
    a generous task timeout, 1 task, max retries 1). Deploying the job must not run it.
  - The runtime service account needs read access to the manuals (Storage Object Viewer on the bucket; it already has
    Storage Object Admin for photos, which covers it) and Vertex AI User for the embeddings.
  - Document in backend/README.md: upload (`gcloud storage cp <file>.pdf gs://<bucket>/manuals/`, or drag it into the
    Cloud console), then run (`gcloud run jobs execute manuals-ingest --region <region> --wait`), then how to read the
    job's logs.
  - **Stretch (only if everything else is done):** run the job automatically when a PDF lands in `manuals/` (Eventarc
    trigger on the bucket). Document the commands; don't make the demo depend on it.
- **Vector index:** a composite vector index on `manual_chunks` (`models` array-contains + `embedding` vector, flat,
  cosine, `EMBED_DIM` dimensions). Put it in `firestore.indexes.json` if the Firebase CLI supports vector indexes,
  otherwise document the exact `gcloud firestore indexes composite create ...` command. Either way, list it under
  "Blocked / needs a human" (it must be created once in the real project).

### Lookup

- `services/manuals.py`:
  `search(question, vehicle, k=MANUAL_TOP_K) -> [{manual_id, title, page, section, text, score}]`.
  - Normalise the vehicle name to the models list (reuse the plate/vehicle helpers' style; "Splendor+" → "Splendor Plus").
  - Embed the question, then `manual_chunks.where(models array_contains model).find_nearest(embedding, COSINE, limit=k)`.
  - Below `MANUAL_MIN_SCORE` similarity → nothing found. Don't pass weak matches to the agent.
  - Reads go through `core.run` like `check_stock`, so the owner's activity feed shows "Raju looked up: clutch free play
    (Splendor Plus owner's manual p.42)".
- **In-memory fake:** extend `FakeQuery` in `app/db.py` with `find_nearest` (cosine over the stored vectors) so every test
  runs without GCP. Check whether the Firestore emulator supports vector queries. If it doesn't, say so in the tick note
  and skip that part on the emulator.

### Agent

- New fast tool **`lookup_manual(question, vehicle="")`** in `tools.py` for the mechanic's Live agent. An empty
  `vehicle` means the current job's vehicle. It returns `{found, answer_sources: [{title, page, section, text}]}`, and
  the Live agent composes the spoken answer itself (no extra sub-agent hop: keep it fast for voice).
- Instruction additions in `agent.py`:
  - For spec or how-to questions, call `lookup_manual`. Answer **only from what it returns**, in one or two sentences,
    number and unit spoken clearly, then the source in a few words ("Splendor Plus manual, page 58").
  - If `found` is false or the passages don't contain the answer: say it isn't in the manual and suggest checking the
    workshop manual. **Never guess a spec from general knowledge.**
  - For procedures: give the steps briefly, offer "next step" one at a time (the mechanic's hands are busy).
  - Never turn a manual lookup into a write (no stage change, no parts logged) unless the mechanic separately asks.
- Optional, if cheap: the owner agent (C04) may use the same tool read-only ("What's the Activa's service interval?").

### Frontend

- Tool chip in the mechanic transcript: **"Manual · Splendor Plus owner's manual p.58"** (and "Not in the manual" when
  nothing is found). The same on the owner voice panel if C04 uses it.
- Demo mode: add one scripted manual Q&A line to `src/demo/voice.js` (e.g. "What's the clutch lever free play?") with a
  clearly made-up demo answer and source, so the feature shows in `npm run demo` too.

### Tests (no GCP)

- Chunker (page and section kept, overlap, Markdown front matter); model-name normalisation.
- `search` on the fake: filters by model, ranks by similarity, applies `MANUAL_MIN_SCORE`. Use a small **fictional**
  test manual in `tests/fixtures/` with a few clearly fake specs; stub embeddings with a deterministic fake (e.g. a
  bag-of-words vector), never real Gemini.
- `lookup_manual` tool: uses the current job's vehicle, returns sources, `found: false` when nothing matches, audit entry.
- Agent: instruction contains the "only from the manual / never guess" rule; the tool is on the mechanic agent.

### Done when

- `python -m app.manuals_ingest` works on Markdown and PDFs into the emulator or fake, from a local folder and from a
  `gs://` prefix (tests use the storage fake), and is safe to re-run.
- `cloudbuild.yaml` deploys the `manuals-ingest` Cloud Run Job alongside the service.
- With the fixture manual, asking a covered question returns the right page; an uncovered one returns `found: false`.
- README: how to add a manual, run ingestion, and create the index; new settings in `.env.example`
  (`EMBED_MODEL`, `EMBED_DIM`, `MANUAL_TOP_K`, `MANUAL_MIN_SCORE`).
- Under "Blocked / needs a human":
  - create the vector index;
  - upload the four owner's manuals to `gs://<bucket>/manuals/` and run the `manuals-ingest` job once (exact commands);
  - review any drafted procedure sheets;
  - real-voice check with these questions: battery voltage and capacity, spark plug gap, front/rear tyre pressure,
    engine oil grade and quantity, clutch lever free play, "How do I replace the clutch plates?", and one question
    that is NOT in the manual (must answer "not in the manual").

---

# Found after the first Google Cloud deploy (Oct 15, 2026)

Work on **one new branch** and open **one PR** for C09–C17; don't push to `main`. Add C09–C17 to `tasks.md` (new section
"Changes after the first cloud deploy"). Tests must still run without GCP. Where only a human can verify (real voice,
real phone calls), say exactly what to check under "Blocked / needs a human".

## C09: Owner Settings page (the auto-approve limit is a setting the owner controls)

**Context:** quotes at or below the garage's `quote_limit` are approved automatically and never reach the customer
(`services/quotes.send_quote`). That rule stays, but the owner had no way to see or change the limit. The team wants
it as a setting in the app.

- New owner tab **Settings** (`/owner/settings`) with a short explanation per field and Save:
  - **Auto-approve limit (₹):** "Quotes up to this amount are approved without asking the customer. 0 = always ask
    the customer." (field `quote_limit`, keep the name).
  - Garage name and city; default customer language; supplier name; reorder quantity; low-stock level (default `low_at`
    for parts that don't set their own).
- Backend: `GET /api/owner/settings` and `PUT /api/owner/settings` (owner only, tenant-checked, validated: limit 0 to
  1,00,000, whole rupees), written through the service layer with an `audit_log` entry ("Asha changed the auto-approve
  limit from ₹500 to ₹0").
- `send_quote` reads the **current** garage setting when the quote is sent (not the copy stored on the job when it was
  created), so a change applies to the next quote immediately.
- When a quote is auto-approved, the mechanic hears "Approved automatically: within the ₹X limit", the quote shows on
  the customer page as approved automatically, and the owner's activity feed says so. (No change to who gets messages.)
- The owner voice agent can answer "what's my auto-approve limit?" (read-only; changing settings stays in the UI).
- Tests: settings read/write/validation/audit, send_quote uses the current setting, owner-only access.

## C10: Washing comes last, just before delivery (bug in the flow)

Real garages wash after the repair. New stage order everywhere:
**intake → service → waiting_approval → washing → ready → done.**
- Backend: `jobs.STAGES`, stage labels, `jobs_by_stage` order, any "next stage" logic, agent instructions and examples
  ("Moving it to washing" now comes after service), the vehicle-history and owner tools.
- Frontend: customer timeline order, owner board columns (Checked in → In service → Washing → Ready), demo script
  (`src/demo/voice.js`: service and the quote happen before washing; then "washing", then "job done"), demo seed,
  `diagrams/job-workflow` text if it lists the order (update the .excalidraw labels only if simple; otherwise note it).
- 3D: `garage3d/layout.js` and `garageScene.js`: station order on the floor becomes front door → service bays → wash
  bay → delivery (move the wash arch/zone next to delivery). `vehicle3d` stage effects unchanged.
- Tests: stage order, demo script end-to-end (vitest + Playwright demo spec), layout tests.

## C11: Language guardrails: always answer in the language the person just used

**Problem:** the agent sometimes answers in a different language from the one it was spoken to in.
**Rule:** reply in the language of the user's **latest** turn: English → English, Hindi → Hindi, Marathi → Marathi,
Hinglish → Hinglish (any language Gemini Live supports follows the same rule). Never switch on its own, not even
because the customer's language, a tool result or earlier turns are in another language. Names, plates, part names and
numbers stay as they are.
- **Instruction:** make this the first and strictest rule for the mechanic agent and the owner agent, with short
  examples (English question → English answer even if the customer speaks Marathi; Hindi question → Hindi answer).
  Tool results that contain other languages (e.g. a Marathi quote text) are summarised in the user's language.
- **Pinned language option:** a language picker on the mechanic and owner voice screens: Auto (default, follow the
  speaker) / English / हिंदी / मराठी. A pinned language is sent with the session start and the gateway sets it in the
  Live config (speech language code, if the model supports it; check the current google-genai `SpeechConfig` /
  Live docs) **and** as an instruction line "Always answer in <language>". Remember the choice per device.
- **Guardrail check:** the gateway already has input and output transcriptions. Add a light check: if the output
  transcription's script clearly differs from the input's (e.g. Devanagari vs Latin) for a turn in Auto mode, log
  `language mismatch` with both snippets and, for the next turn only, add a one-line system reminder to the session.
  No heavy language-detection library: a script check (Devanagari vs Latin characters) is enough; Hindi vs Marathi
  can't be told apart this way, so leave those to the instruction.
- Tests: instruction text, pinned language reaches the Live config, the script check (English vs Devanagari).
  Real-voice check under Blocked.

## C12: Customer page: English by default, Hindi switch

- The customer page (`/j/:token`) is **English by default**, with a visible **English | हिंदी** switch in the header.
  The choice is remembered on that device. All page text (headings, stage names, buttons, toasts, bill labels) has
  English and Hindi strings: a small `src/i18n.js` dictionary, no i18n library.
- Quote and message texts on the page: show the English text by default and the Hindi version when Hindi is chosen.
  Backend: the customer view returns `text_en` and `text_hi` for quotes and messages (translate once when the quote is
  sent, with the existing `gemini.translate`, and store both). Keep the WhatsApp/notify message in the customer's
  language setting as today, but new customers default to `lang: "en"` unless the mechanic says otherwise.
- Tests: the switch, both strings present for every key (a test that fails on a missing Hindi key), the view returns
  both texts.

## C13: Consumables (nuts, bolts, gaskets…) are used with a part and must show in stock and cost

**Problem:** fitting a clutch plate also uses a gasket, bolts, washers, oil and so on. Today only the main part leaves
stock, so the owner can't see what a job really costs.
- Inventory items get an optional **`with`** list: consumables used each time the part is fitted, e.g.
  `clutch-splendor.with = [{part_id: "gasket-clutch-cover", qty: 1}, {part_id: "bolt-m6", qty: 4}, {part_id:
  "engine-oil-800", qty: 1}]`. Each consumable is a normal inventory item with `kind: "consumable"`, a price, a cost
  (`cost` = what the garage paid) and `billable` (true: charged to the customer, false: garage's own cost).
- `log_part_used` decrements the main part **and** its consumables (qty × parts fitted) in one service call, adds
  billable ones to the bill as their own lines, and records non-billable ones on the job as `consumables` with their
  cost. Idempotent like today (same request_id = no second decrement). If a consumable is out of stock, still log the
  main part, record the shortfall and flag it as low stock (the agent says so in one short line).
- `draft_quote` includes billable consumables as lines, so the customer sees the real total before approving.
- Owner: job viewer and dashboard show **parts + consumables + labour = bill** and **cost of parts used** (from
  `cost`), and the margin per job; the Stock tab lists consumables with their own low-stock flags; the owner voice
  agent can answer "what did J-1042 cost us?".
- Seed realistic consumables for both garages (gaskets, M6/M8 bolts, washers, split pins, grease, chain lube, engine
  oil top-up) and `with` lists for the common jobs (clutch plate, brake shoes, chain kit, oil change). Prices clearly
  plausible, not from any real catalogue.
- Agent: when logging a part, it reads back the main part only, plus "and the usual fittings" if there are any; it
  doesn't list every bolt aloud.
- Tests: decrement of part + consumables, billing split, idempotency, shortfall, quote lines, owner cost/margin.

## C14: Manual first, then (with the mechanic's OK) a web search for known fixes

**Flow** for questions about a specific problem or spec:
1. Call `lookup_manual` first (as today).
2. If the manual has it: answer from it with the page (as today).
3. If not: say it isn't in the manual and **ask** "Shall I search online for known causes and fixes?" Do nothing until
   the mechanic says yes.
4. On yes: call a new **`web_search_fixes(question, vehicle)`** tool. It runs a small sub-agent on TEXT_MODEL with ADK's
   built-in **`google_search`** tool (Gemini grounding with Google Search). Built-in tools can't sit on the same agent as
   function tools, so it is its own agent wrapped as an AgentTool, like the Quote/Comms sub-agents. It returns 2–3
   short "common causes and known fixes" points with the source site names.
5. The Live agent speaks them briefly, says they're **from the web, not the manual**, one step at a time, and never
   presents them as a diagnosis. Safety rule: anything about brakes, fuel leaks or electrical/EV high-voltage parts
   ends with "check against the workshop manual".
- The transcript chip shows "Web · <site names>" (like the "Manual · …" chip); the audit log records the search.
- Config: `WEB_SEARCH_MODEL` (default TEXT_MODEL). Check the current ADK docs for `google_search` usage with Vertex AI.
- Tests: stub the sub-agent; the instruction contains the ask-first rule; the tool is never called without a "yes"
  turn (check the instruction and the tool's guard: it requires `confirmed=True`, which the agent passes only after
  the mechanic agreed).
- Demo mode: one scripted exchange (manual miss → "search online?" → "yes" → two made-up fixes clearly labelled demo).

## C15: AI front desk: customers can call the garage and the AI answers

A customer calls the garage; the AI answers in the caller's language and can:
- tell them their vehicle's status (look up by the caller's phone number or plate),
- send them their status link or the pending quote again (via `notify()`, like today),
- take a request for a price: draft an estimate from stock prices for common jobs and send it **to the owner for
  confirmation** (owner sees it as an agent ask on the dashboard; on confirm it goes to the customer),
- take a message / book a drop-off time (a simple `bookings` collection the owner sees),
- "transfer": when it can't help, it creates a callback request for the owner ("Call back Ramesh about …") and tells
  the caller someone will call back. No real call transfer.

**How (Google stack, no new paid service needed for the demo):**
- A new **`front_desk`** ADK agent (Live model, its own small tool set over the existing services; read-only except
  `send_status_link`, `send_quote_again`, `request_estimate`, `book_dropoff`, `request_callback`). Callers are
  identified only by phone number; it never reveals another customer's data.
- **Web call** for the demo: a "Call the garage" button on the customer page and on the landing page (C16) opens a
  voice call to `/ws/voice` with role `caller` (short-lived anonymous token tied to the garage; rate-limited).
- **Real phone line (document, don't build):** README section on connecting a phone number later through a telephony
  provider that streams call audio over WebSockets (e.g. Twilio Media Streams or Exotel) into the same gateway, with
  the audio format conversion needed (8 kHz μ-law ↔ 16 kHz PCM). Note it under Blocked as a post-hackathon step.
- Owner: a "Calls" list on the dashboard (who called, summary, what the AI did, callback requests); activity feed lines.
- Tests: tool isolation (a caller can only see their own jobs), estimate goes to the owner first, callback created,
  the gateway picks the front-desk agent for role `caller`. Demo mode: a scripted call.

## C16: A landing page that explains the product in seconds, then "Try it"

Today `/` is a small home page with role cards. Replace it with a real product landing page for judges and new
visitors, then lead into the hands-on part.
- **Few words, mostly visuals.** Sections:
  1. Hero: one line ("The AI co-worker for India's garages: mechanics talk, it does the paperwork, customers approve
     from their phone") + a short looping animation of the flow (mechanic speaks → job card appears → customer approves
     on a phone → owner's floor updates).
  2. The problem in three relatable picture cards (greasy hands and a ringing phone; a customer worried about a surprise
     bill; an owner with no idea what's on the floor). One short sentence each.
  3. How it works: a simple diagram (SVG, built in the page, no image files needed) of mechanic ↔ voice agent ↔
     customer page ↔ owner floor, with the manual lookup and approvals marked.
  4. What makes it different: 3–4 tiles (hands-free in Hindi/Marathi/English; nothing done without the customer's OK;
     answers from the vehicle's manual; live 3D view of the garage).
  5. **Try it**: three cards (Mechanic · Customer · Owner), each saying exactly what you'll do and see there ("Hold the
     orb and say: …", "Approve a quote", "Watch the floor live"), plus the "Call the garage" button from C15. In demo
     mode these open the demo; in production they open the real screens.
  6. A small footer: built on Gemini, ADK, Cloud Run, Firestore.
- Design: use the existing tokens and type (`styles.css`), the orange accent, light and dark mode; fast (no new heavy
  libraries; reuse three.js only lazily if at all); great on phones and on a laptop; respects reduced motion.
- The "Try it" screens must then match what the page promised: check the copy against the real flows.
- Tests: Playwright (phone + desktop): the page renders, no sideways scroll, each Try-it card opens the right screen.

## C17: Owner records: transactions, vehicles, customers, staff

**Problem:** the owner can see today, the floor and stock, but none of the garage's records: past jobs and bills,
vehicle history, the customer list, employees and what they've done. The data is already in Firestore (`jobs`,
`customers`, `mechanics`, `audit_log`, `quotes`); this is about showing it well.

New owner tabs (the tab bar scrolls sideways on phones; keep Today first): **Today · Floor · Jobs · Customers ·
Vehicles · Staff · Stock · Settings**.
- **Jobs (transactions):** every job, newest first, with filters (today / this week / this month / custom dates; open /
  closed; mechanic) and search (plate, customer, job id). Each row: date, job id, vehicle + plate, customer, mechanic,
  status, bill (parts, consumables from C13, labour), time taken. Totals for the filter at the top (jobs, revenue,
  average bill, average time). Click → the job detail (timeline with time per stage, parts, quotes and decisions,
  messages sent, photos, 3D view). **Export CSV** for the current filter.
- **Customers:** name, phone, language, vehicles, number of visits, total spent, last visit; search; click → their
  vehicles and jobs, and a "Send status link" for an open job.
- **Vehicles:** every plate the garage has seen: model, owner, visits, last service date and what was done, total spent;
  click → full service history (the same data `get_vehicle_history` uses).
- **Staff:** how many mechanics, and for each: jobs finished (today / this week / this month), jobs open now, average
  time per job, revenue on their jobs, parts logged, last active; a simple bar chart per mechanic for the period.
  **Add mechanic** (name, phone, PIN) using the existing `POST /api/owner/mechanics` (`people.invite_mechanic`), and
  deactivate a mechanic (they can no longer sign in; their history stays).
- Backend: owner-only, tenant-checked read endpoints in `routes_owner.py` over the service layer: `GET
  /api/owner/jobs?from=&to=&status=&mechanic=&q=&cursor=` (paginated, 50 per page), `GET /api/owner/customers`, `GET
  /api/owner/customers/{id}`, `GET /api/owner/vehicles`, `GET /api/owner/vehicles/{plate}`, `GET
  /api/owner/staff?period=`, `POST /api/owner/mechanics/{uid}/deactivate`. Compute aggregates on read for now (small
  garages); keep them in one module (`services/reports.py`) so moving to stored daily totals later is a contained
  change. Add any Firestore composite indexes the queries need to `firestore.indexes.json` and list them under Blocked.
- Owner voice agent: read-only tools for "how many jobs did Raju finish this week?", "how much did we make this
  month?", "when did MH12AB1234 last come in?".
- Demo mode: the demo backend answers the same endpoints from the demo store; add a few weeks of plausible closed
  jobs, customers and vehicles to the demo seed so the pages aren't empty (keep the demo job script unchanged).
- Design: same look as the dashboard (cards, tables that turn into cards on phones, no sideways scroll), loading and
  empty states, numbers formatted in ₹ and Indian digit grouping (`format.js`).
- Tests: each endpoint (filters, pagination, tenant isolation: garage B never sees garage A), aggregates, CSV, the
  deactivate rule (deactivated mechanic's PIN login fails), Playwright for each tab on phone and desktop.
