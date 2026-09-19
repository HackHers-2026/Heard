# Architecture

## Overview

Heard is **two frontends over one backend**:

- **Chrome extension** — the *live* surface. Sits on top of Google Slides,
  captures the user's speech during practice, and renders Gemini coaching as
  pop-ups.
- **Web app** — the *reflective* surface. Shows the transcript + AI feedback as
  a chat, a final summary and score, the per-domain leaderboard, and DMs.
- **FastAPI backend** — the shared brain. Owns auth, data, scoring, and the
  integrations (ElevenLabs, Gemini, Backboard, TigerTable).

## The practice loop

1. **Pre-training** — `GET /training/pre/{domain}` → Gemini returns domain-specific
   prep coaching + a checklist.
2. **Start a run** — `POST /sessions` creates a `PracticeSession` and a Backboard
   memory thread so coaching is context-aware across runs.
3. **Live feedback** — the extension transcribes speech (Web Speech API in the
   demo; ElevenLabs server-side via `POST /feedback/transcribe` in production) and
   sends chunks to `POST /feedback/live`. Gemini replies with a short tip → pop-up.
4. **Post-training** — on stop, `POST /feedback/summarize` builds a summary +
   score, recomputes the user's rolling **improvement score**, and syncs the run
   to TigerTable. The web app shows the chat + report.
5. **Community** — the leaderboard (`GET /leaderboard/{domain}`) ranks women by
   improvement; top performers are recommended as mentors and reachable via DMs
   (`/messages`).

## Data model

| Model | Purpose |
| --- | --- |
| `User` | Practicer or mentor; holds `domain` + rolling `improvement_score` |
| `PracticeSession` | One run; links to a Backboard thread + final `score` |
| `Transcript` | Captured speech for a session |
| `Feedback` | AI items — `live` pop-ups and the `summary` report |
| `Message` | DMs between users |

## Integration points (`backend/app/services/`)

| Module | Role | Fallback when no key |
| --- | --- | --- |
| `elevenlabs.py` | Speech → text | Stub transcript string |
| `gemini.py` | Live tips, summary/score, pre-training | Deterministic canned coaching |
| `backboard.py` | Per-user conversation memory | In-process dict |
| `tigertable.py` | Structured analytics / leaderboard source | Local row mirror |
| `scoring.py` | Improvement-score math (rewards upward trends) | — (pure logic) |

Every integration degrades gracefully so the full app is runnable and demoable
before any keys are added.

## Auth

JWT (HS256). Issued by `/auth/login` (OAuth2 password form). Both frontends store
the token — the web app in `localStorage`, the extension in `chrome.storage.local`
(owned by the service worker so it's the single network caller).

## Scaling notes / TODO

- Swap SQLite → Postgres via `DATABASE_URL` (SQLModel handles the rest).
- Move live feedback to a WebSocket for lower latency.
- Confirm real Backboard + TigerTable API surfaces (endpoints are best-guess).
- Add rate limiting + audio streaming for ElevenLabs.
- Notifications for DMs and mentor requests.
