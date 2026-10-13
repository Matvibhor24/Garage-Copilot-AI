# Suggestions

Collected from planning and the codebase review (Oct 10, 2026). Ordered by what matters most for the demo freeze on **Oct 14** and submission on **Oct 18**. Tick or delete items as you act on them.

## 1. Before the demo freeze (Oct 14)

- [ ] **Test real voice end to end. This is the top risk.** Nothing AI-related has run against real Gemini yet; every test uses stand-ins. Fastest path: get a Gemini API key from AI Studio, run the backend locally (see "Running locally" below), talk to `/mechanic` through a laptop mic, then a phone + Bluetooth headset. Technical merit is 40% of the score and depends on this working.
- [ ] **Measure latency on the quote step.** "Show Ramesh the worn plate" goes Live agent → Quote sub-agent → Comms sub-agent: three model hops. If it feels slow, let the Live agent call `draft_quote` / `send_quote` directly and keep the sub-agents for non-voice work.
- [ ] **Translation runs mid-conversation.** `create_job`, `send_quote` and `close_job` call Gemini to translate the customer message (Shree Auto's customers are Marathi) before the tool returns. If it adds noticeable delay, translate after replying to the mechanic, or accept English for the demo.
- [ ] **Pick the region setup.** `cloudbuild.yaml` puts Cloud Run in Mumbai (`asia-south1`) but Gemini in `us-central1`, so every voice turn crosses continents. Check what the Live API supports and keep the two as close as possible.
- [ ] **Decide the model names** (env vars only, no code change): `TEXT_MODEL` / `VISION_MODEL` default to `gemini-2.5-flash`, while the solution doc says Gemini 3 Flash. `LIVE_MODEL` differs between Vertex AI and AI Studio (see `tasks.md`).
- [ ] **Fix the small dev-login bug:** in `backend/app/auth.py` `claims_from_header`, a dev token sets `name` to the user id, so the agent calls Raju "m-raju" in local runs. Look the real name up from the mechanics doc (or put it in the dev token).
- [ ] **Do the Google Cloud setup** listed under "Blocked / needs a human" in `tasks.md` (project, Firebase web app, phone sign-in, bucket, secrets, service accounts, Cloud Build trigger, scheduler). Assign one person to it.
- [ ] **Test on real phones:** Android Chrome and iOS Safari, Bluetooth headset, hands-free vs push-to-talk with garage noise. Keep confirmations short ("Got it: clutch plate, ₹650").
- [ ] **Rule from the build plan:** anything not working by the night of Oct 13 goes in the deck as "roadmap", not in the video.

## 1b. Changes found in the first local run (Oct 11). Full details in `changes.md`

- [ ] **C01 Laptops and desktops:** screens are phone-width columns on big screens. Make all three screens work well on any device.
- [ ] **C02 Agent repeats replies 2–3 times (sometimes).** Most likely two voice sessions open at once (React StrictMode double-mount in dev, mode switch, or two tabs); otherwise audio forwarded twice by the gateway, or the model restating after tool results.
- [ ] **C03 Agent speaks a bit fast:** slow it slightly via a Live speech setting if available, else instruction + voice choice, as config. Not by slowing browser playback (lowers pitch).
- [ ] **C04 Owner voice agent:** mic on the owner dashboard; agent answers questions about operations from real data (summary, jobs, approvals, stock, activity); can answer reorder asks; can't do mechanic actions.
- [ ] **C05 Customer Approve/Decline card stays on screen** after choosing (real backend, dev mode). Find the root cause, fix, test.

## 2. Demo and video

- **Demo mode (`npm run demo`) is scripted, not AI.** Pre-written lines play on each button press and the browser's own voice reads the replies. Use it to show the UI or as a backup, but don't present it as the live agent. The video should show real Gemini doing real tool calls.
- **Filming:** confirm a real garage soon. Backup plan: a friend's bike, real tools and greasy hands, with recorded garage noise playing during voice takes so the noise-handling claim is honest. Screen-record the phone and dashboard during every take.
- **Language:** pitch as multilingual and demo Hinglish. One short Marathi line in the video shows the multilingual claim is real.
- **Show multi-tenancy:** two seeded garages exist (Shree Auto, Ganesh Motors). A 5-second shot of the second garage's dashboard not seeing Shree Auto's jobs proves isolation.

## 3. Pitch and documents

- **Don't claim the product is "perfect" or quote scale numbers.** Show scale-readiness instead: the "Scale later" table in `diagrams/architecture.png` (each step is a setting or a swap, not a rewrite), plus an honest "what breaks first and how we'd fix it" slide. Judges trust evidence over claims.
- **Update the solution doc.** Its Architecture section still shows the old "root agent + 4 specialists" design and the open Next.js vs React question. Use `diagrams/architecture.png` and `AGENTS.md` instead.
- **Business model:** owner subscription, free for 1 mechanic, ₹499/month per garage. Later: revenue from parts reordering via the low-stock asks.
- **Product name** is still open. Ideas: Ustaad (what mechanics call the master mechanic; recommended), Mistri, Saathi, GaadiGuru. Avoid "Chotu", which is the nickname for underage shop helpers.

## 4. Code: fine for now, know about it

- **Stock race:** two mechanics using the last unit at the same instant could take stock to −1 (`services/inventory.py`, no transaction). OK for the demo.
- **Nudge sweep** loops over every garage in one request. Fine for two garages; needs paging or fan-out for many.
- **npm reports 4 high-severity vulnerabilities in the frontend.** Checked Oct 11: it is one issue in `@grpc/grpc-js` (server-side gRPC advisories GHSA-m9gg-hp2v-232j and GHSA-f596-whhp-79r4), counted once per package in the chain firebase → firestore-compat → firestore → grpc-js. It does not apply in the browser, where Firestore does not use grpc-js. Don't run `npm audit fix --force`: it downgrades firebase 13 → 9.14 and breaks the app. Re-check after a future `npm update firebase`.
- **Messages to mechanics are polled every 2 s** by the voice gateway. Fine for the demo; a Firestore listener would be faster later.

## 5. Running locally

| Level | What works | Needs |
|---|---|---|
| A. Demo mode | All screens, scripted, no AI | `cd frontend && npm install && npm run demo` |
| B. Real backend, no AI | Real API + database: PIN login, owner dashboard, customer link, approvals | Firestore emulator (`npx firebase-tools@14`, needs Java + Node) + `python -m app.seed` + backend with `AUTH_DISABLED=1 LINK_SECRET=dev` + `npm run dev` |
| C. Real voice | The actual product through a laptop mic | B + `GOOGLE_API_KEY` from AI Studio and an AI-Studio `LIVE_MODEL` |

Notes: `DB_BACKEND=memory` can't be seeded from a separate process, so use the emulator for B and C. Commands are in `backend/README.md` and `frontend/README.md`.

## 6. Repo and accounts

- **Make the repo public before Oct 18** (required): repo Settings → General → Danger Zone → Change visibility.
- **The personal access token** must not expire before Oct 18.
- **Git commit email** on Gaurav's Mac is `96624731+gauravmkale@users.noreply.github.com`; make sure it is on the GitHub account, or commits won't link to the profile.
- **Gaurav's Mac only:** `~/.npm` has files owned by root, so `npm install` fails. Fix once with `sudo chown -R $(id -u):$(id -g) ~/.npm`.
