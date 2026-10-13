# Deploying GarageCopilot to Google Cloud

A step-by-step manual for the team. Do the steps in order; each one says **who**, **what to run**, and **what you
should see**. Budget **2–3 hours** the first time. After that, a redeploy is one command (step 16).

```
Phone / laptop browser
   │  https://garagecopilot.web.app          (Firebase Hosting: the React app)
   │      /api/**  ─────rewrite────────────►  Cloud Run "garage-copilot" (asia-south1): FastAPI + ADK agents
   │  wss://garage-copilot-…run.app/ws/voice ►  (voice goes straight to Cloud Run: Hosting can't pass WebSockets)
   │                                            │
   │                                            ├─► Vertex AI Gemini (us-central1): Live voice, text, vision, embeddings
   │                                            ├─► Firestore: garages, jobs, quotes, stock, manual chunks (+ vector index)
   │                                            ├─► Cloud Storage bucket: photos/ and manuals/ (private, signed URLs)
   │                                            └─► Secret Manager: link-secret
   └── Firestore realtime listeners (read-only for clients, firestore.rules)

Cloud Scheduler ──every 5 min──► Cloud Run /api/tasks/sweep (approval nudges)
Cloud Run Job "manuals-ingest" ──► reads gs://…/manuals/*.pdf ──► Firestore manual chunks
Cloud Build ──► tests, builds the image, pushes to Artifact Registry, deploys the service and the job
```

Who's who in this guide:

- **Deployer**: whoever runs the commands, from a clone of the team's GitHub repo. Must have the **Owner** role on the
  `garagecopilot` project; if you created the project, you already have it.
- **Manuals:** the four owner's manual PDFs are **not in the repo** (copyrighted). Get them from the team privately
  (e.g. a shared Google Drive folder) before step 13 and put them in `backend/manuals/pdf/` (git-ignored).

**Files that are never in the repo, on purpose:** `frontend/.env.local` (you create it in step 10), any service
account key file, and the manual PDFs.

---

## 0. Values used everywhere

| Name | Value | Notes |
| --- | --- | --- |
| Project ID | `garagecopilot` | |
| Cloud Run region | `asia-south1` (Mumbai) | `firebase.json` and `cloudbuild.yaml` assume it |
| Gemini region | `us-central1` | Live voice isn't offered in every region |
| Cloud Run service | `garage-copilot` | |
| Image repo | `garage-copilot` (Artifact Registry, asia-south1) | |
| Runtime service account | `garage-copilot-run@garagecopilot.iam.gserviceaccount.com` | what the backend runs as |
| Scheduler service account | `garage-copilot-scheduler@garagecopilot.iam.gserviceaccount.com` | |
| Bucket | `garagecopilot-garage-photos` | photos/ and manuals/; if your bucket has another name, see step 7 |
| Secret | `link-secret` | signs the customer links |
| App URL | `https://garagecopilot.web.app` | Firebase Hosting default domain |

---

## 1. Before you start (Owner, 10 min)

1. **Billing:** Cloud console → Billing: the project must be linked to the billing account with the hackathon credits.
2. **If the Deployer is not the project owner, give them the Owner role:** Cloud console → IAM & Admin → IAM → **Grant access** → the Deployer's Google
   account → role **Owner** → Save.
3. **Deployer installs the tools on their Mac** (skip what's already there):

   ```bash
   brew install --cask google-cloud-sdk     # gcloud
   brew install node uv
   gcloud auth login                        # opens the browser: sign in with the Owner account
   gcloud config set project garagecopilot
   gcloud auth application-default login    # lets local scripts use the same account
   ```

   ✅ `gcloud config list` shows `project = garagecopilot` and your email.

> Never use or share the old `garage-backend.json` key for this. In the cloud, the backend runs as the runtime
> service account and needs no key file at all.

---

## 2. Shell variables (Deployer, every new terminal)

Paste this at the start of every terminal session you use for this guide:

```bash
export PROJECT=garagecopilot
export REGION=asia-south1
export RUN_SA=garage-copilot-run@$PROJECT.iam.gserviceaccount.com
export SCHED_SA=garage-copilot-scheduler@$PROJECT.iam.gserviceaccount.com
export BUCKET=garagecopilot-garage-photos
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
echo $PROJECT_NUMBER   # a long number; if empty, step 1 isn't done
```

---

## 3. Turn on the services (Deployer, 5 min)

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com storage.googleapis.com \
  iamcredentials.googleapis.com cloudscheduler.googleapis.com firebase.googleapis.com \
  firebasehosting.googleapis.com identitytoolkit.googleapis.com
```

✅ Ends with `Operation ... finished successfully` (can take a minute or two).

**Firestore:** the database already exists (the demo garages were seeded into it). Check: Cloud console → Firestore →
you see `garages`, `phone_index`. If there is no database, create one: **Native mode**, location `asia-south1`.

---

## 4. Service accounts and roles (Deployer, 10 min)

```bash
# What the backend runs as
gcloud iam service-accounts create garage-copilot-run --display-name="GarageCopilot backend"
for ROLE in roles/datastore.user roles/aiplatform.user roles/secretmanager.secretAccessor roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$RUN_SA --role=$ROLE --condition=None
done
# It signs photo URLs and login tokens as itself
gcloud iam service-accounts add-iam-policy-binding $RUN_SA \
  --member=serviceAccount:$RUN_SA --role=roles/iam.serviceAccountTokenCreator

# What Cloud Scheduler uses to call the sweep endpoint
gcloud iam service-accounts create garage-copilot-scheduler --display-name="GarageCopilot scheduler"

# What Cloud Build runs as (new projects use the Compute Engine default account): let it deploy
export BUILD_SA=$PROJECT_NUMBER-compute@developer.gserviceaccount.com
for ROLE in roles/run.admin roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$BUILD_SA --role=$ROLE --condition=None
done
gcloud iam service-accounts add-iam-policy-binding $RUN_SA \
  --member=serviceAccount:$BUILD_SA --role=roles/iam.serviceAccountUser
```

✅ Each command prints an updated policy (`bindings: ...`). "already exists" on `create` is fine.

---

## 5. The link secret (Deployer, 2 min)

```bash
openssl rand -base64 48 | tr -d '\n' | gcloud secrets create link-secret --data-file=-
```

✅ `Created version [1] of the secret [link-secret].` Don't print it or paste it anywhere.

---

## 6. Image repository (Deployer, 1 min)

```bash
gcloud artifacts repositories create garage-copilot --repository-format=docker --location=$REGION
```

---

## 7. The bucket for photos and manuals (Deployer, 5 min)

A photos bucket may already exist from earlier testing. Check its name:

```bash
gcloud storage buckets list --format='value(name,location)'
```

- If it's **`garagecopilot-garage-photos`**: nothing to change.
- If it has **another name**: either create the expected one (below), or use yours and add
  `,_GCS_BUCKET=<your-bucket>` to the `--substitutions` in steps 9 and 16.

Create it if needed (private, Mumbai):

```bash
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access --public-access-prevention
```

Give the backend access to it (photos are written here; manuals are read from `manuals/`):

```bash
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=serviceAccount:$RUN_SA --role=roles/storage.objectAdmin
```

---

## 8. Firebase on the same project (Owner or Deployer, 15 min, in the browser)

1. https://console.firebase.google.com → **Add project** → choose the existing **garagecopilot** project (don't create
   a new one) → continue. Google Analytics: not needed.
2. **Authentication** → Get started → Sign-in method → enable **Phone**.
   - For the demo, add **test phone numbers** (Authentication → Sign-in method → Phone → *Phone numbers for testing*),
     e.g. `+91 98000 00001` with code `123456`. Test numbers need no SMS and no reCAPTCHA on stage.
   - Authentication → Settings → **Authorized domains**: `garagecopilot.web.app` and `garagecopilot.firebaseapp.com`
     are there by default; add any other domain you use.
3. **Project settings** (gear icon) → *Your apps* → **Add app** → Web (`</>`) → name `GarageCopilot` → don't tick
   Hosting setup here → Register. Copy the four values from the config it shows (`apiKey`, `authDomain`,
   `projectId`, `appId`). They are not secret, but keep them out of git anyway (`.env.local` is ignored).

---

## 9. Deploy the backend to Cloud Run (Deployer, 10–15 min)

From the repo root, on an up-to-date `main`:

```bash
git checkout main && git pull
gcloud builds submit --config cloudbuild.yaml --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
```

This runs the backend tests, builds `backend/Dockerfile`, pushes the image and deploys the `garage-copilot` service
(min 1 instance, so there's no cold start in the middle of the demo).

✅ The log ends with `SUCCESS`. Get the URL and check it:

```bash
export RUN_URL=$(gcloud run services describe garage-copilot --region $REGION --format='value(status.url)')
echo $RUN_URL                    # https://garage-copilot-xxxxxxxx-el.a.run.app
curl $RUN_URL/health             # {"ok":true}
```

---

## 10. Deploy the frontend to Firebase Hosting (Deployer, 10 min)

1. Create `frontend/.env.local` (never committed) with the values from step 8 and the Cloud Run URL from step 9:

   ```bash
   VITE_API_BASE=
   VITE_WS_BASE=wss://garage-copilot-xxxxxxxx-el.a.run.app
   VITE_FIREBASE_API_KEY=...
   VITE_FIREBASE_AUTH_DOMAIN=garagecopilot.firebaseapp.com
   VITE_FIREBASE_PROJECT_ID=garagecopilot
   VITE_FIREBASE_APP_ID=...
   VITE_FIRESTORE_EMULATOR_HOST=
   ```

   `VITE_API_BASE` stays empty: Hosting forwards `/api/**` to Cloud Run (`firebase.json`). `VITE_WS_BASE` is the
   Cloud Run URL with `https` replaced by `wss`.

2. Build and deploy (the Hosting site and the Firestore security rules):

   ```bash
   cd frontend && npm ci && npm run build && cd ..
   npx firebase-tools@14 login
   npx firebase-tools@14 deploy --only hosting,firestore:rules --project garagecopilot
   ```

✅ `Deploy complete!` and `Hosting URL: https://garagecopilot.web.app`. Open it: the home page loads.

---

## 11. Demo data and the owner's phone (Deployer, 5 min)

The two demo garages are already in Firestore. To reset them to a clean state at any time (it overwrites the demo
garages' config, people, stock and history; it doesn't delete jobs created later):

```bash
cd backend
unset FIRESTORE_EMULATOR_HOST AUTH_DISABLED          # make sure you're NOT pointing at the emulator
GOOGLE_CLOUD_PROJECT=garagecopilot uv run python -m app.seed
cd ..
```

**Owner sign-in:** the owner signs in by phone, and the phone must be in `phone_index`. The seed uses Asha =
`+919800000001`, Vikram = `+919800000002`. Either add those numbers as Firebase **test numbers** (step 8), or use real
phones: Firestore console → `phone_index` → copy the document to an ID with the real number (`+91…`), same fields.

**Mechanics** sign in with name + PIN (`1234` from the seed; set `SEED_PIN` before seeding to change it).

---

## 12. Approval reminders: Cloud Scheduler (Deployer, 5 min)

```bash
gcloud scheduler jobs create http garage-sweep --location=$REGION --schedule="*/5 * * * *" \
  --uri="$RUN_URL/api/tasks/sweep" --http-method=POST \
  --oidc-service-account-email=$SCHED_SA --oidc-token-audience="$RUN_URL/api/tasks/sweep"
```

Then redeploy the backend once so it knows the audience (step 16 with
`,_SCHEDULER_AUDIENCE=$RUN_URL/api/tasks/sweep` added to `--substitutions`).

✅ Cloud console → Cloud Scheduler → `garage-sweep` → **Force run** → status *Success*.

---

## 13. Vehicle manuals (Deployer, 15 min, after the first backend deploy)

The backend deploy (step 9) also creates the **`manuals-ingest` Cloud Run Job**. It reads the PDFs from the private
bucket, has Gemini read every page (scanned pages and spec tables too), and stores searchable passages in Firestore.

1. **Vector index** (once; takes a few minutes to build). From the repo root:

   ```bash
   npx firebase-tools@14 deploy --only firestore:indexes --project garagecopilot
   gcloud firestore indexes composite list     # wait until the manual_chunks index says READY
   ```

2. **Upload the four manuals** (private bucket; never commit them):

   ```bash
   gcloud storage cp backend/manuals/pdf/*.pdf gs://$BUCKET/manuals/
   gcloud storage ls gs://$BUCKET/manuals/     # four files, with the exact names listed in backend/manuals/catalog.json
   ```

3. **Run the import** (about 10 minutes for the four manuals):

   ```bash
   gcloud run jobs execute manuals-ingest --region $REGION --wait
   ```

   ✅ The job's logs (Cloud Run → Jobs → manuals-ingest → Logs) show one line per manual: `ingested … N page(s)`.
   A line ending `(N page(s) from the PDF text: transcription failed)` means Gemini failed on some pages; once fixed,
   re-run with `gcloud run jobs execute manuals-ingest --region $REGION --args=-m,app.manuals_ingest,--force --wait`.

4. **Spot-check:** Firestore console → `manual_chunks` → filter `manual_id` = `hero-splendour-plus-owners-manual` →
   the specifications page: rows read like `Spark plug gap: 0.6-0.7 mm`.

Adding a manual later: add its exact file name to `backend/manuals/catalog.json` (commit + redeploy), upload it, run the
job again (unchanged manuals are skipped).

## 14. Smoke test on a real phone (both, 15 min)

On 4G, not office Wi-Fi, with a Bluetooth headset:

- [ ] `https://garagecopilot.web.app` loads; "Add to home screen" works.
- [ ] Owner: phone sign-in → dashboard shows Shree Ganesh's stock and history.
- [ ] Mechanic: Raju + PIN → voice screen → "Splendor aaya hai, MH12AB1234, clutch slip ho raha hai"
      ("A Splendor is in, MH12AB1234, the clutch is slipping") → job card appears on the owner's dashboard live.
- [ ] Customer link from the job → opens on a second phone → stage updates live.
- [ ] Quote above the limit → customer Approve → mechanic hears it.
- [ ] Photo upload → shows on the customer page.
- [ ] Manual question: "Splendor ka spark plug gap?" ("Spark plug gap for the Splendor?") → answer with the page number (after step 13).
- [ ] Owner voice: "Aaj kitne bikes aaye?" ("How many bikes came in today?")
- [ ] Second garage (Vikram) can't see the first garage's jobs.

---

## 15. If something goes wrong

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `PERMISSION_DENIED` in Cloud Build at the deploy step | build service account roles | Step 4, the Cloud Build part |
| Build fails at `test` | a backend test fails | Run `cd backend && uv run pytest -q` locally, fix, push |
| `/health` works but every API call is 401 | not signed in / Firebase config wrong | Check `frontend/.env.local`, rebuild, redeploy hosting |
| Voice: "Connection lost" immediately | `VITE_WS_BASE` wrong or still `https://` | Must be `wss://<cloud-run-host>`; rebuild + redeploy hosting |
| Voice connects but Gemini errors in the logs | Vertex AI not enabled / role missing / model not in region | Step 3 + `roles/aiplatform.user` (step 4); `GOOGLE_CLOUD_LOCATION=us-central1` |
| PIN login or customer live updates fail with a signing error | Token Creator role or IAM Credentials API missing | Step 3 (`iamcredentials`) and step 4 (`serviceAccountTokenCreator`) |
| Photo upload fails | bucket name or bucket role | Step 7 |
| Customer links point to localhost | `PUBLIC_BASE_URL` | Defaults to `https://garagecopilot.web.app`; set `_PUBLIC_BASE_URL` if you use another domain |
| Phone OTP: reCAPTCHA / "domain not authorized" | authorized domains | Step 8.2 |
| `/api` calls 404 on the Hosting domain | Cloud Run service name/region doesn't match `firebase.json` | Must be `garage-copilot` in `asia-south1` |

Logs: Cloud console → Cloud Run → `garage-copilot` → **Logs** (or `gcloud run services logs read garage-copilot --region $REGION`).

---

## 16. Redeploying after changes

- **Backend** (and the manuals job): `git pull` on `main`, then
  `gcloud builds submit --config cloudbuild.yaml --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)`
  (add `,_SCHEDULER_AUDIENCE=...` and `,_GCS_BUCKET=...` if you used them).
- **Frontend:** `cd frontend && npm run build && cd .. && npx firebase-tools@14 deploy --only hosting --project garagecopilot`.
- **Optional, automatic:** Cloud console → Cloud Build → Triggers → *Connect repository* (GitHub
  the team's repo) → trigger on push to `main` with `cloudbuild.yaml`, substitution
  `_SCHEDULER_AUDIENCE` set. Then every merge to `main` redeploys the backend.

---

## 17. After the hackathon

- `min-instances=1` keeps one backend instance running all the time (it uses credits). After judging:
  `gcloud run services update garage-copilot --region $REGION --min-instances=0`.
- Delete the old local key once nobody needs it: Cloud console → IAM → Service accounts → the backend account → Keys.
- Before making the repo public: check that `git log` has no keys, `.env*` files or manual PDFs
  (`git log --all --stat | grep -iE '\.pdf|\.env|\.json'`).
