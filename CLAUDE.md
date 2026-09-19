# CLAUDE.md

Guidance for AI coding agents (Claude, Cursor, etc.) working in the **Heard** repo.

## What this project is

A safe space for women to practice speaking up — with AI encouragement before,
real-time coaching during, and community + mentorship after.

Built for the **developHer** track @ Hackhers 2026: *empower women through
education, career growth, and connection.*

**Core problem:** Women struggle with confidence to speak up in work, personal,
and public settings.

## Product flows

| # | Flow | Platform |
|---|------|----------|
| 1 | Pre-speech encouragement — "Encourage me" button or speech planner | webapp |
| 2 | Real-time feedback — volume + pace nudges every 2 min | chrome extension |
| 3 | Post-speech report — 5-metric score + mentor suggestions | webapp |
| 4 | Community feed — public posts, liked + tagged by career/topic | webapp |
| 5 | User profile — radar chart, mentor toggle, auth | webapp |

## Speech metrics

1. **Clarity** — sentence structure and coherence
2. **Volume** — loudness consistency (Web Audio API amplitude)
3. **Pace** — words-per-minute vs comfortable range
4. **Confidence** — filler words (um, uh), hedging language
5. **Structure** — intro / body / conclusion (scored from transcript)

---

## Architecture (read `docs/ARCHITECTURE.md` for depth)

Two frontends, one backend:

- `backend/` — **FastAPI + SQLModel**. Auth, data, scoring, all integrations.
- `web/` — **React + Vite + TypeScript** dashboard (post-speech reflection).
- `extension/` — **Chrome Manifest V3**. Captures speech via Web Speech API +
  volume via Web Audio API (`AudioContext` / `AnalyserNode`) in parallel.

Data flow: extension captures speech + amplitude → backend transcribes
(ElevenLabs) and coaches (Gemini, with Backboard memory) → live nudges to
extension every 2 min, summary + 5-metric report to web app; synced to TigerTable.

**Key fact:** runs with **no API keys** — every service has a stub fallback.
Build UI and flows first; wire real keys via `backend/.env` later.

## Run it

```bash
# Backend
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt && copy .env.example .env
uvicorn app.main:app --reload            # http://localhost:8000/docs

# Web
cd web && npm install && npm run dev     # http://localhost:5173

# Extension
# chrome://extensions → Developer mode → Load unpacked → extension/
```

**Key fact:** the app runs with **no API keys**. Every external service has a
stub fallback (see the table in `docs/ARCHITECTURE.md`). Build UI and flows
first; wire real keys via `backend/.env` later.

## Where things live

| Area | Location |
|------|----------|
| API endpoints + data models | `backend/` |
| AI coaching, transcription, memory, analytics | `backend/app/services/` |
| Web dashboard | `web/` |
| Chrome extension (speech, volume, overlay) | `extension/` |

## Conventions

- **Backend:** async route handlers; DB access via `get_session`; auth via
  `get_current_user`. Keep third-party calls inside `services/` — routers
  should not call httpx/SDKs directly.
- **Every integration must keep its no-key stub fallback.** Don't break local dev.
- **Web:** functional components + hooks; all HTTP goes through `web/src/api.ts`.
  No secrets in the frontend.
- **Extension:** content scripts stay thin and talk to backend only via
  `chrome.runtime.sendMessage` to the service worker (single token owner).
- **Secrets:** never commit real keys. Only `.env.example` is tracked.

## Guardrails

- Ask before adding heavy dependencies or new services.
- Keep changes minimal and localized; match existing style.
- This is Windows/PowerShell — chain shell commands with `;`, not `&&`.
- Don't commit `heard.db`, `node_modules/`, `dist/`, or any `.env`.
# Heard — Hackathon Context

**One-liner:** A safe space for women to practice speaking up — with AI encouragement before, real-time coaching during, and community + mentorship after.

**Track:** Empower women through education, career growth, and connection.

**Core problem:** Women struggle with confidence and capability to speak up in work, personal, and public settings.

---

## Team

| Person | Role | Task file |
|--------|------|-----------|
| Ran | Backend | `tasks/01-backend.md` |
| TBD | Frontend | `tasks/02-frontend.md` |
| TBD | Chrome extension | `tasks/03-chrome.md` |

**Read `tasks/00-contracts.md` first** — it defines the data models and API interfaces everyone depends on.

---

## Product flows (5)

| # | Flow | Entry point | Platform |
|---|------|-------------|----------|
| 1 | Pre-speech encouragement | "Encourage me" button → AI chatbot, or plan a speech | webapp |
| 2 | Real-time feedback | Live volume + pace analysis, updated every 2 min, ≤10-word nudge | chrome extension |
| 3 | Post-speech report | 5-metric scored summary + mentor connection suggestions | webapp |
| 4 | Community feed | Reports posted publicly; liked, tagged by career/topic | webapp |
| 5 | User profile | Radar/pentagon chart of top-3 speeches; mentor toggle; LinkedIn login | webapp |

---

## Speech metrics (5 dimensions)

1. **Clarity** — how well-structured and understandable the speech is
2. **Volume** — loudness consistency (from audio level)
3. **Pace** — words-per-minute vs. comfortable range
4. **Confidence** — hedging language, filler words (um, uh, like)
5. **Structure** — intro / body / conclusion presence

---

## Tech stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | React + Next.js | Deployed on Vercel (free tier) |
| Backend | TBD (Node/Python) | API server; keep it thin |
| Database | Supabase | Postgres; auth + realtime built in |
| Analytics | TigerData → Supabase | User speech stats and aggregates; see [TigerData Supabase docs](https://www.tigerdata.com/docs/integrate/data-engineering-etl/supabase) |
| AI analysis | Gemini API | Real-time 2-min transcript → nudge; post-speech 5-metric scoring |
| Pre-speech AI | Gemini API | Encouragement chatbot |
| Auth | Supabase magic link | POC default; LinkedIn OAuth via Auth0 is stretch (after 10PM) |
| Transcript capture | Web Speech API | Browser-native; runs inside the Chrome extension |
| Volume capture | Web Audio API (`AudioContext` / `AnalyserNode`) | Parallel stream alongside speech recognition; samples amplitude every frame |
| Chrome extension | Manifest V3 | Hosts the real-time feedback UI |

---

## Decisions

- **Real-time feedback** — automatic push every 2 min, no tap required
- **Mentor DM** — in-app message
- **Auth** — Supabase magic link for POC; LinkedIn OAuth via Auth0 is stretch (after 10PM)
- **Profile average** — top-3 speeches, outliers dropped; TigerTable aggregation is stretch (after 10PM)
- **Structure metric** — scored from transcript; Gemini detects opening/body/conclusion

## Stretch goals (after 10PM only)

- LinkedIn OAuth via Auth0
- TigerTable analytics pipeline
- Facial expression analysis (out of scope for this POC)

---

## Task files

```
tasks/
  00-contracts.md    Data models + API interfaces — read this first
  01-backend.md      Backend — API routes, scoring, Gemini integration
  02-frontend.md     Frontend — web dashboard, Vercel deploy
  03-chrome.md       Chrome — Manifest V3, real-time audio + nudge UI
```

## Quick start

1. Read this file.
2. Read `tasks/00-contracts.md` before touching any code.
3. Read your task file.
4. Secrets go in `backend/.env` — never commit. Ask Ran for key names.
5. Happy path first; skip edge cases until the core flow works end-to-end.
