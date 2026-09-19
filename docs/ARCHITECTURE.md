# Architecture

## Overview

Heard is **two frontends over one backend**, centered on **Backboard as a
stateful coaching brain** wrapped around Gemini:

- **Chrome extension** — the *live* surface. Sits on the user's active tab, captures speech via Web Speech API + volume via Web Audio API, and shows real-time coaching nudges as an overlay.
- **Web app** — the *reflective* surface. Pre-speech encouragement, post-speech 5-metric report, community feed, mentor connections, and profile radar chart.
- **FastAPI backend** — the shared brain. Auth, data, scoring, and the Backboard + Gemini coaching layer.

The realtime feedback loop is the heart of the product: transcription
(ElevenLabs) → per-session queue worker → **Backboard** (persistent
assistant + thread + cross-session memory) → **Gemini** (reasoning) →
structured feedback → DB + WebSocket → Chrome sidebar. See
[Coaching brain](#coaching-brain-backboard--gemini) below.

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

> **Realtime path.** The extension side panel streams mic audio over the
> `/ws/stt` WebSocket. The backend proxies it to ElevenLabs, buffers committed
> transcripts into ~60s `RealtimeSegment`s, and coaches each one through
> Backboard + Gemini (below). The `POST /api/speech/segment` route is the
> simpler, synchronous fallback used when not streaming.

---

## Coaching brain (Backboard + Gemini)

Backboard is the **stateful memory assistant** at the center of Heard — not a
decorative extra API. It gives every user a persistent coach that remembers
their patterns across sessions. Gemini is the model that produces the coaching;
Backboard supplies the persistent state, cross-session memory, and tool calling
around it (`llm_provider="google"`).

```
Assistant  = the user's long-term coach   (one per user → User.backboard_assistant_id)
  └─ Thread   = one practice session        (Speech.backboard_thread_id)
       └─ Message = one 60-second segment    (RealtimeSegment)
```

Memories are stored at the **assistant level** and shared across that assistant's
threads, so session 3 draws on what the coach learned in sessions 1–2. Each user
gets their **own** assistant so memory is never mixed between users.

**Memory is split into two modes on purpose:**

| When | Mode | Behavior |
|------|------|----------|
| During the session (per segment) | `Readonly` | Retrieve past coaching memories; do **not** write per-minute noise |
| At session end (one call) | `Auto` | Extract durable, communication-specific memories for next time |

The assistant is created once per user with a coach `system_prompt`, a custom
`custom_fact_extraction_prompt`, and a `custom_update_memory_prompt` (so memories
stay communication-specific), plus one function tool:

- **`get_recent_performance()`** — pulls exact recent scores from the DB (memory
  is for patterns; the DB is the source of truth for precise analytics). Backboard
  requests it via a tool call; the backend executes it locally and submits the result.

**Non-blocking, in-order pipeline** — one queue worker per session guarantees
minute 1 → 2 → 3 reach the Backboard thread in order, and transcription is never
blocked while Gemini/Backboard think:

```
RealtimeSegment ─▶ asyncio Queue ─▶ CoachingWorker (one per session)
                                        │
                          Backboard thread + memory ──▶ Gemini
                                        ▼
        { focus_area, nudge, evidence, progress, next_minute_goal, scores }
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                              ▼
   RealtimeSegment.nudge + feedback_json            WebSocket → Chrome sidebar
```

The sidebar shows only the short `nudge`; the full structured JSON is saved to
`RealtimeSegment.feedback_json` for the report. Files:
`services/backboard.py` (assistant lifecycle, `coach_segment`,
`finalize_session`, tool), `services/coaching.py` (queue worker),
`services/segmenter.py` (buffering + `on_segment` hook), `routers/stt.py` (WebSocket wiring).

---

## Data model (8 tables, all in Supabase)

| Model | Purpose |
|-------|---------|
| `User` | Auth identity; `is_mentor` toggle; `career_tag`; `backboard_assistant_id` (long-term coach) |
| `Speech` | One recording session; `status`: live → done; `backboard_thread_id` (this session's thread) |
| `SpeechMetrics` | 5-dim scores + overall + summary + suggestions |
| `RealtimeSegment` | ~60s transcript chunk + audio stats + `nudge` + `feedback_json` (full structured coaching) |
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
| `backboard.py` | **Stateful coaching brain** — per-user assistant, per-session thread, cross-session memory, `get_recent_performance` tool; routes Gemini via `llm_provider="google"` | Deterministic stub coaching (assistant/thread skipped) |
| `coaching.py` | Per-session queue worker — in-order, non-blocking segment coaching + WebSocket push | Runs against stub coaching |
| `segmenter.py` | Buffers committed transcripts into ~60s `RealtimeSegment`s; fires `on_segment` hook | Always active |
| `gemini.py` | encourage / nudge / score / chat (non-realtime flows) | Canned stubs for all functions |
| `scoring.py` | top_speeches / average_metrics / find_mentors | Pure Python, no key needed |
| `elevenlabs.py` | Realtime + one-shot STT | Stub transcript stream — pipeline still runs |
| `tigertable.py` | Analytics pipeline (TigerData / TimescaleDB) | No-op stub |

Every service degrades gracefully — the full app runs and demos without any keys,
including Backboard.

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
- Realtime segment nudges already stream over the `/ws/stt` WebSocket; `get_recent_performance` can later query TigerData instead of SQLite.
- Wire TigerData for real-time leaderboard aggregation (stretch, `tasks/13-stretch-tigertable.md`).
- LinkedIn OAuth via Auth0 (stretch, `tasks/12-stretch-linkedin-auth.md`).
