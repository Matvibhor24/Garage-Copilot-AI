# GarageCopilot frontend

One React (Vite) PWA with three screens:

| Route | Who | What |
| --- | --- | --- |
| `/mechanic` | mechanic on the shared garage phone | name + PIN, then the voice screen (orb, live transcript, job strip, photo, typing fallback). The shift belongs to this tab and this screen: leaving it (Back/Forward, a link, another site, closing the tab) signs the mechanic out; only a reload keeps it |
| `/owner` (`/owner/stock`) | garage owner | phone OTP, then the live dashboard: tiles, jobs board (tap a job for 3D), agent asks, activity + messages, stock, and an **Ask** button that opens a voice panel to ask about the day |
| `/j/:token` | the vehicle's owner, no login | live status, quote with photo, one-tap Approve, final bill |

Design: warm neutrals, one orange accent, light/dark, big touch targets. Everything is plain CSS in
`src/styles.css` (tokens at the top); animations respect `prefers-reduced-motion`.

## Run it

```
cd frontend
npm install
npm run demo        # no backend, no Firebase: an in-browser fake backend plays the demo job
npm run dev         # against the local backend on :8000 (Vite proxies /api and /ws)
npm test            # vitest
npm run e2e         # Playwright: the demo job across all three screens (demo mode)
npm run build       # production build in dist/
```

**Demo mode** (`npm run demo`) is the quickest way to see everything: open `/mechanic` (Raju, PIN 1234),
`/owner` and `/j/demo-J-1042` in three tabs. Each push of the orb plays the next line of the job in
`diagrams/job-workflow.png`; tabs update each other live. Reset it from the mechanic's ⋯ menu.
On `/owner`, **Ask** opens the owner's voice panel; each push asks the next demo question ("How many bikes are in
today?", "What's pending approval?", "How much did we make today?", "Which parts are low?", "How long did Ramesh's
job take?", "Yes, reorder the clutch plates."), answered from the demo data.

Every screen works from phone to desktop: phone-first CSS with `min-width` layouts on top (two columns for the
customer page, a jobs side panel on the mechanic screen, wider owner dashboard). Playwright runs a Pixel 7 and a
1440×900 desktop.

## How data flows

```
screen -> src/data/api.js (REST, ID token) -> backend view (e.g. /api/owner/dashboard)
          src/data/live.js: Firestore onSnapshot on the same docs -> refetch   (polls every 4 s without Firebase)
voice  -> src/voice/client.js: mic AudioWorklet -> 16 kHz PCM16 -> wss /ws/voice -> 24 kHz PCM16 playback
          (one socket per screen; hands-free does not send the mic while the agent speaks, so a speaker's echo
          can't make Gemini answer itself)
```

The backend computes every view; Firestore listeners are only a "something changed" signal, so the
screens and the backend never disagree about shapes. All writes go through the REST API (rules make
Firestore read-only for clients).

| File | What |
| --- | --- |
| `src/config.js` | `VITE_*` settings |
| `src/data/auth.js` | sign-in modes: `firebase`, `dev` (no Firebase, backend `AUTH_DISABLED=1`), `demo` |
| `src/data/firebase.js` | lazy Firebase init, persistent offline cache, emulator hook |
| `src/demo/` | the fake backend + scripted voice for demo mode |
| `src/voice/` | real voice client and PCM helpers |
| `public/sw.js`, `public/manifest.webmanifest` | offline app shell, installable PWA |

## Connect to Google Cloud (for whoever wires up the project)

1. **Firebase web app:** in the Firebase console add a Web app to the GCP project, copy its config into
   `frontend/.env.local` (`VITE_FIREBASE_API_KEY`, `_AUTH_DOMAIN`, `_PROJECT_ID`, `_APP_ID`).
   Enable **Phone** sign-in and add the Hosting domain to Authorized domains.
2. **Backend URL:** deploy the backend (`cloudbuild.yaml`). Set `VITE_WS_BASE=wss://<cloud-run-host>`
   because Firebase Hosting rewrites do not carry WebSockets. REST goes through the Hosting rewrite
   (`/api/**` → Cloud Run service `garage-copilot` in `asia-south1`, see `firebase.json`), so
   `VITE_API_BASE` stays empty. If you host the frontend elsewhere, set `VITE_API_BASE` to the Cloud Run
   URL and the backend's `CORS_ORIGINS` to the frontend origin.
3. **Backend settings that must match:** `PUBLIC_BASE_URL=https://<hosting-domain>` (customer links),
   `AUTH_DISABLED` unset. The runtime service account needs *Service Account Token Creator* so PIN login
   and customer live sessions can mint custom tokens.
4. **Deploy:** `npm run build` in `frontend/`, then from the repo root
   `npx firebase-tools deploy --only hosting,firestore:rules`.
5. **First owner sign-in:** the owner's phone must be in `phone_index` (the seed adds Asha's
   `+919800000001`; change it to a real number). After OTP, the app calls `/api/auth/claim` and refreshes the token.

Local end to end without Firebase: Firestore emulator + `python -m app.seed` + backend with
`AUTH_DISABLED=1 LINK_SECRET=dev` + `npm run dev`. Owners get a "Continue as Asha" button and mechanics
sign in with the seeded PIN; voice needs Gemini credentials on the backend.

## Not yet checked on real hardware

Mic capture and playback on Android Chrome / iOS Safari with a Bluetooth headset, the hands-free mode in a
noisy garage, and Firebase phone OTP (reCAPTCHA) on the real domain.
