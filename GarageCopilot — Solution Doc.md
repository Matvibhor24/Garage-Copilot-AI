# GarageCopilot — Solution Doc

Oct 1, 2026 · @Gaurav

## Pitch and problem

**GarageCopilot (working name) is a hands-free, voice-first AI back office for Indian two- and four-wheeler garages.** Mechanics talk to it through a Bluetooth headset; it opens job cards, checks stock and prices, gets customer approval for extra work, and keeps the owner's books and the customer's status page up to date. Theme: **Future of Work & Enterprise Productivity**.

- **Problem:** in a small garage the mechanic is also the storekeeper, estimator and phone operator. Every stock check, price lookup or "can we go ahead?" call means stopping work, washing hands and picking up a phone. Jobs stall waiting for customer replies, and the owner has no live view of jobs, stock or time spent.
- **Buyer:** the garage owner (efficiency, fewer disputes, stock control). **User:** the mechanic (never touches the phone). **Beneficiary:** the vehicle owner (live status, itemised quotes, nothing done without consent).
- **Positioning:** workflow augmentation, not diagnostics. Light Q&A about a vehicle is allowed; repair diagnosis is out of scope.

## Demo story (the 3-minute video)

One bike, one mechanic, hands never touch the phone:

1. **Intake:** "New bike, Splendor Plus, MH12 AB 1234, owner Ramesh, 98xxxxxx, complaint: clutch slipping, general service." A job card is created and Ramesh gets a WhatsApp-style link to a live status page.
2. **Status updates:** "Started service." (and, after the repair, "Moving it to washing") The page timeline updates and time per stage is logged.
3. **Stock check:** "Do we have a clutch plate set for Splendor? Price?" Agent: "Two in stock, ₹650, labour ₹300."
4. **Approval:** the job is over the pre-approved budget, so the agent sends Ramesh an itemised quote. He taps Approve; the mechanic hears "Ramesh approved, go ahead."
5. **Auto-logging:** "Used one clutch plate set." Stock decrements; the job bill updates.
6. **Close-out:** "Job done." Final bill to the customer, status page shows ready for pickup, owner dashboard shows the job closed and stock low.

Stretch, if time allows: a customer asks "how much for a brake pad change?" via the web voice agent; it drafts a quote, confirms it with the owner by voice, and replies.

## Features and scope

Must-haves ship by Oct 15; stretch only after the demo path works end to end.

| Feature | What it does | Scope |
| --- | --- | --- |
| Voice copilot (mechanic app) | Mobile web app, Bluetooth headset, Hindi / English / Hinglish, push-to-talk fallback | Must |
| Job cards | Create from voice; vehicle, owner, phone, complaint, stage, mechanic, timestamps | Must |
| Customer status page | Public link per job: timeline of stages, quote, final bill | Must |
| Inventory Q&A + updates | "Do we have X? Price?"; parts used decrement stock; low-stock flags | Must |
| Quote + approval | Itemised parts + labour; customer approves on a web page; mechanic told by voice | Must |
| Owner dashboard | Open jobs by stage, pending approvals, low stock, time per job, day's revenue | Must |
| Audit log | Every agent action recorded with who, what, when | Must |
| WhatsApp delivery | Send status link and quote via WhatsApp (sandbox or simulated send in demo) | Stretch |
| Customer voice agent | Inbound price queries via web voice, owner confirms quote | Stretch |
| Light vehicle Q&A | Torque specs, service intervals, grounded answers | Stretch |
| Telephony, payments, multi-branch, diagnostics | — | Out |

## Architecture

&#91;embedded content: architecture · 3 clients, 1 service, 4 agents\]

Every agent action writes to Firestore, and real-time listeners push changes to the dashboard and status page, so nobody refreshes anything. Quotes above a per-garage threshold always pause for customer approval; the audit log records each tool call.

## Tech stack

All-Google, as the rules require (Gemini models, deployed on GCP).

| Layer | Choice | Notes |
| --- | --- | --- |
| Voice | Gemini Live API (native audio), streamed over WebSocket | Hindi/Hinglish; test with real garage noise in week 1 |
| Reasoning | Gemini 3 Flash (fast tool calls); Gemini 3.1 Pro for quote drafting if needed |  |
| Agents | ADK (Gemini Enterprise Agent Platform), orchestrator + 4 specialists | Tools are plain Python functions over Firestore |
| Backend | Python FastAPI on Cloud Run | One service: agent, REST API, WebSocket |
| Data | Firestore: `garages`, `jobs`, `stages`, `inventory`, `quotes`, `customers`, `audit_log` | Real-time listeners drive the dashboard and status page |
| Frontend | Next.js or React on Firebase Hosting: mechanic app (PWA), owner dashboard, customer page | Shared Firebase Auth for owner and mechanic |
| Messaging | Approval link by SMS/WhatsApp sandbox; simulated send for the demo | Swap in WhatsApp Business API later |
| Observability | Cloud Logging + the audit log shown in the dashboard | Supports the auditability story |
| Repo / CI | Public GitHub repo, Cloud Build deploy on push | Required deliverable |

## Build plan and owners

&#91;embedded content: build plan · Oct 1 to Oct 18\]

The whole demo path must work by Oct 14; the last four days are for filming and documents only.

- **Member A (backend + AI):** Cloud Run service, ADK agents and tools, Firestore schema, Gemini Live voice gateway, audit log.
- **Member B (frontend + demo):** mechanic PWA, owner dashboard, customer status and approval page, video, deck, vision PDF.
- **Both:** seed data (one garage, \~30 parts with prices), a daily 15-minute sync, test on a real headset every other day.

**Submission checklist (due Oct 18, 2026)**

- [ ] Deployed prototype link (Cloud Run + Firebase Hosting)
- [ ] Public GitHub repo with README and setup steps
- [ ] Public demo video, under 3 minutes
- [ ] Vision document (PDF)
- [ ] Pitch deck

## Judging fit, risks, open decisions

| Criterion (weight) | How we score |
| --- | --- |
| Technical merit & Gen AI (40%) | Live voice + multi-agent ADK with real tool calls, human-in-the-loop approval, audit trail |
| Problem alignment & impact (25%) | Mechanic time saved per job; fewer stalled jobs; transparent pricing for customers |
| Innovation (25%) | Hands-free agent for an informal-sector workforce, in Hinglish |
| UX & design (10%) | Zero-touch for the mechanic; one-tap approval for the customer |

**Risks and fallbacks**

- Speech in a noisy garage → push-to-talk, short confirmations ("Got it: clutch plate, ₹650"), test real audio by Oct 6.
- Live API latency or session limits → fall back to record-and-send voice turns.
- WhatsApp approval delays → approval via web link; WhatsApp is only the delivery channel.
- Looks like a CRUD app → film a real mechanic with greasy hands; show the agent doing the calling.

**Open decisions**

- [ ] Final product name
- [ ] Next.js vs plain React for the three frontends
- [ ] One real garage to film the demo in (who and when)
- [ ] Confirm the theme change is accepted on the portal
