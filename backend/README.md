# Heard — Backend (FastAPI)

One API that serves both frontends: the **web app** and the **Chrome extension**.

## Stack
- FastAPI + SQLModel (SQLite by default, swap `DATABASE_URL` for Postgres)
- JWT auth (shared by web app + extension)
- Service layer for **ElevenLabs** (STT), **Gemini** (coaching), **Backboard** (memory), **TigerTable** (analytics)

## Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # then fill in your API keys
uvicorn app.main:app --reload
```

Docs: http://localhost:8000/docs · Health: http://localhost:8000/health

> The app runs **without any API keys** — every external service has a stub
> fallback so you can build the UI first and wire real keys in later.

## Key endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/signup`, `/auth/login` | Auth, returns JWT |
| POST | `/sessions` | Start a practice run (creates a Backboard thread) |
| POST | `/feedback/transcribe` | Upload an audio chunk → ElevenLabs text |
| POST | `/feedback/live` | Transcript chunk → Gemini live pop-up tip |
| POST | `/feedback/summarize` | End of run → summary + score + leaderboard update |
| GET | `/sessions/{id}/feedback` | The AI "chat" for a run |
| GET | `/leaderboard/{domain}` | Ranked by improvement score |
| GET | `/leaderboard/{domain}/mentors` | Recommended mentors |
| POST | `/messages` | DM a mentor |
| GET | `/training/pre/{domain}` | Pre-practice coaching |

## Layout

```
app/
  main.py            # app + router wiring
  config.py          # env settings
  database.py        # engine/session
  models.py          # User, PracticeSession, Transcript, Feedback, Message
  schemas.py         # API contracts
  core/security.py   # hashing + JWT
  routers/           # auth, sessions, feedback, leaderboard, messages, training
  services/          # elevenlabs, gemini, backboard, tigertable, scoring
```
