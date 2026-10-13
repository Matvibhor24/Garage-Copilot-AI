# GarageCopilot

Voice-first AI back office for small Indian garages: a mechanic talks through a headset; an agent opens
job cards, checks stock, gets the customer's approval for extra work, and keeps the owner's dashboard and
the customer's status page live. Google AI Builders Cup entry (Gemini, ADK, Cloud Run, Firestore).

- `backend/`: FastAPI + ADK on Cloud Run ([README](backend/README.md))
- `frontend/`: React PWA for mechanic, owner and customer ([README](frontend/README.md))
- `tasks.md`: what is done, what is next, what is blocked on a human
- `diagrams/`: architecture and the demo job end to end

Quick look without any cloud setup: `cd frontend && npm install && npm run demo`.
