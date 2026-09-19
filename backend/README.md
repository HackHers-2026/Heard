# Heard — Backend

FastAPI service for both frontends: the **web app** and the **Chrome extension**.

## Stack

| | |
|---|---|
| Framework | FastAPI + SQLModel |
| DB | SQLite (dev) → Supabase Postgres (prod) |
| Auth | Supabase magic link → JWT validation |
| AI | Google Gemini (encourage, nudge, score) |
| Transcription | ElevenLabs Scribe STT (stub fallback built in) |
| Memory | Backboard — stateful Gemini sessions (stretch) |

## Run locally

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in API keys (app works without them)
uvicorn app.main:app --reload
```

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

**No API keys needed** — every external service has a stub fallback.

## API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/encourage` | JWT | Pre-speech encouragement (quick or plan mode) |
| POST | `/api/speech/start` | JWT | Start a live speech session |
| POST | `/api/speech/segment` | session_token | Submit 2-min transcript chunk + audio stats → nudge |
| POST | `/api/speech/end` | session_token | End session, trigger async scoring |
| GET | `/api/speech/{id}/report` | JWT | 5-metric report (ready after `/end`) |
| POST | `/api/speech/{id}/chat` | JWT | Chat with AI coach (preptalk / activetalk / talksummary) |
| GET | `/api/speech/{id}/chat` | JWT | Fetch chat thread, optionally filter by ?phase= |
| GET | `/api/feed` | JWT | Paginated community posts |
| POST | `/api/feed` | JWT | Share a speech to the feed |
| POST | `/api/feed/{id}/like` | JWT | Toggle like on a post |
| GET | `/api/profile/{user_id}` | JWT | Radar chart data + top speeches |
| POST | `/api/mentor/connect` | JWT | Request mentor connection |
| GET | `/health` | — | Health check |

## Speech metrics

Scoring is **hybrid** — 3 metrics are deterministic, 2 use Gemini:

| Metric | Source |
|--------|--------|
| Volume | `avg_volume` + `volume_variance` from Web Audio API |
| Pace | word count ÷ `duration_seconds` vs 120–150 wpm target |
| Confidence | filler word regex density (`um`, `uh`, `like`, `basically`…) |
| Clarity | Gemini — sentence coherence, vocabulary |
| Structure | Gemini — detectable intro / body / conclusion |

Only a 600-char excerpt goes to Gemini for scoring (~300 tokens vs ~2k for full transcript).

## Layout

```
app/
  main.py             app + router registration
  models.py           8 SQLModel tables (User, Speech, SpeechMetrics, …, ChatMessage)
  dependencies.py     get_current_user (Supabase JWT), get_session
  config.py           env settings (pydantic-settings)
  database.py         engine + get_session generator
  routers/
    encourage.py
    speech.py
    feed.py
    profile.py
    mentor.py
    chat.py
  services/
    gemini.py         encourage / nudge / score (hybrid)
    scoring.py        top_speeches / average_metrics / find_mentors
    elevenlabs.py     STT stub
    backboard.py      Gemini memory (stretch)
    tigertable.py     analytics (stretch)
migrations/
  001_initial_schema.sql        7 core tables
  002_chat_memory.sql           chatmessage table + session_hash index
  003_chat_memory_phase.sql     adds phase + summary columns
tests/
  conftest.py         session-scoped DB setup
  test_setup.py       health + route registration (spec 01)
  test_db.py          all 7 tables + audio fields (spec 02)
  test_auth.py        JWT validation + user upsert (spec 03)
  test_routes.py      all routes stub-mode (spec 04)
  test_gemini.py      encourage / nudge / score stubs (spec 05)
  test_scoring.py     top_speeches / average / mentors (spec 06)
  test_component.py   30 end-to-end tests, all 5 product flows (spec 07)
```

## Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/          # 59 tests, all green, no API keys needed (chat router tested via component tests)
```

## Env vars

See `.env.example`. Minimum for live AI features:

```
SUPABASE_URL=https://ytmrxkzczjsiorfcsbmc.supabase.co
SUPABASE_JWT_SECRET=   # Dashboard → Settings → API → JWT Secret
GEMINI_API_KEY=        # aistudio.google.com
```
