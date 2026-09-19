# Architecture

## Overview

Heard is **two frontends over one backend**:

- **Chrome extension** — the *live* surface. Sits on the user's active tab, captures speech via Web Speech API + volume via Web Audio API, and shows real-time Gemini coaching nudges as an overlay.
- **Web app** — the *reflective* surface. Pre-speech encouragement, post-speech 5-metric report, community feed, mentor connections, and profile radar chart.
- **FastAPI backend** — the shared brain. Auth, data, all AI calls, scoring, and chat memory.

---

## The practice loop

```
User ──▶ [preptalk]   POST /api/encourage  (quick button or speech planner)
                      POST /api/speech/{id}/chat  phase=preptalk

         [activetalk] POST /api/speech/start       → speech_id + session_token
                      POST /api/speech/segment ×N  → nudge (every 2 min)
                      POST /api/speech/{id}/chat   phase=activetalk
                      POST /api/speech/end          → triggers async scoring

         [talksummary] GET /api/speech/{id}/report → 5-metric report
                       POST /api/mentor/connect    → request mentor DM
                       POST /api/feed              → share to community
                       POST /api/speech/{id}/chat  phase=talksummary
```

---

## Data model (8 tables, all in Supabase)

| Model | Purpose |
|-------|---------|
| `User` | Auth identity; `is_mentor` toggle; `career_tag` |
| `Speech` | One recording session; `status`: live → done |
| `SpeechMetrics` | 5-dim scores + overall + summary + suggestions |
| `RealtimeSegment` | ~2-min transcript chunk + audio stats (volume, variance) |
| `CommunityPost` | Shared speech linked to feed; tagged by career/topic |
| `Like` | User ↔ CommunityPost many-to-many (toggle) |
| `MentorConnection` | Mentor request; status: pending / accepted / declined |
| `ChatMessage` | Chat history per speech session; `phase` labels each exchange |

---

## Scoring — hybrid (no LLM for 3 of 5 metrics)

| Metric | Source | How |
|--------|--------|-----|
| Volume | Deterministic | `avg_volume` + `volume_variance` from Web Audio API → `_range_score()` |
| Pace | Deterministic | `word_count / duration_seconds * 60` vs 120–150 wpm target |
| Confidence | Deterministic | Filler word regex density (`um`, `uh`, `like`, `basically`…) |
| Clarity | Gemini flash | 600-char excerpt only (~300 tokens) |
| Structure | Gemini flash | Same call as clarity — intro/body/conclusion detection |

Only one Gemini call per speech for scoring. Stub mode returns 70 for clarity/structure.

---

## Chat memory (`ChatMessage`)

Every chat exchange is persisted. On each call:
1. Fetch last 10 rows (`session_hash = sha256(speech_id)[:16]`)
2. Pass as `history=` to `model.start_chat()` — Gemini has conversational context
3. Save `role=user` + `role=model` rows, both tagged with `phase` and a 3-5 word `summary`

Three phases shape Gemini's persona:

| Phase | When | Tone |
|-------|------|------|
| `preptalk` | Before recording starts | Warm, encouraging, detailed |
| `activetalk` | During recording | Terse, ≤15 words per nudge |
| `talksummary` | After report is ready | Reflective, growth-focused |

---

## Integration points (`backend/app/services/`)

| Module | Role | Fallback when no key |
|--------|------|----------------------|
| `gemini.py` | encourage / nudge / score / chat | Canned stubs for all 4 functions |
| `scoring.py` | top_speeches / average_metrics / find_mentors | Pure Python, no key needed |
| `elevenlabs.py` | STT (stretch) | Empty string — extension uses Web Speech API |
| `backboard.py` | Gemini session memory (stretch) | Not active — ChatMessage table used instead |
| `tigertable.py` | Analytics pipeline (stretch) | No-op stub |

Every service degrades gracefully — the full app runs and demos without any keys.

---

## Auth

Supabase magic link → JWT (HS256). `get_current_user` in `dependencies.py`:
1. Decodes Bearer token using `SUPABASE_JWT_SECRET`
2. Reads `sub` (UUID) and `email` from payload
3. Upserts a `User` row on first login

For POC: segment and end endpoints accept any bearer token (the `session_token` = `speech_id`). Full auth on all other endpoints.

Stretch: LinkedIn OAuth via Auth0 (see `tasks/12-stretch-linkedin-auth.md`).

---

## API surface

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/encourage` | JWT | Quick encouragement or speech outline |
| POST | `/api/speech/start` | JWT | Start session → speech_id + session_token |
| POST | `/api/speech/segment` | session_token | 2-min chunk + audio stats → nudge |
| POST | `/api/speech/end` | session_token | End session, trigger async scoring |
| GET | `/api/speech/{id}/report` | JWT | 5-metric report |
| POST | `/api/speech/{id}/chat` | JWT | Send chat message, get reply + summary |
| GET | `/api/speech/{id}/chat` | JWT | Fetch chat thread (filter by ?phase=) |
| GET | `/api/feed` | JWT | Paginated community feed |
| POST | `/api/feed` | JWT | Share speech to feed |
| POST | `/api/feed/{id}/like` | JWT | Toggle like |
| GET | `/api/profile/{user_id}` | JWT | Radar chart data + top-3 speeches |
| POST | `/api/mentor/connect` | JWT | Request mentor connection |
| GET | `/health` | — | Health check |

---

## Migrations

| File | What it does |
|------|-------------|
| `001_initial_schema.sql` | All 7 core tables |
| `002_chat_memory.sql` | `chatmessage` table + index on `session_hash` |
| `003_chat_memory_phase.sql` | Adds `phase` + `summary` columns to `chatmessage` |

All applied to Supabase project `ytmrxkzczjsiorfcsbmc`.

---

## Deployment

| Layer | Host | Notes |
|-------|------|-------|
| Web app | Vercel | Root dir: `web/`, auto-deploys on push to main |
| Backend | Railway / Render | `Procfile`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| DB | Supabase Postgres | `DATABASE_URL` env var switches from SQLite |
| Secrets | Vercel + Railway dashboards | Never in code; see `tasks/10-vercel-deploy.md` |

---

## Scaling notes

- Swap SQLite → Postgres: set `DATABASE_URL` to Supabase connection string — SQLModel handles the rest.
- Move segment nudges to WebSocket for sub-second latency.
- Wire TigerTable for real-time leaderboard aggregation (stretch, `tasks/13-stretch-tigertable.md`).
- LinkedIn OAuth via Auth0 (stretch, `tasks/12-stretch-linkedin-auth.md`).
