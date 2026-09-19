# CLAUDE.md

Guidance for AI coding agents (Claude, Cursor, etc.) working in the **Heard** repo.

## What this project is

Heard helps women build confidence speaking up. Users rehearse a pitch over
Google Slides and get warm, real-time AI coaching, then track improvement and
connect with mentors. Built for the **developHer** track (Hackhers 2026).

**Tone matters.** This is a supportive, confidence-building product for women.
Any user-facing copy or AI prompts must be encouraging and never harsh. When
editing coaching prompts, preserve that voice.

## Architecture (read `docs/ARCHITECTURE.md` for depth)

Two frontends, one backend:

- `backend/` — **FastAPI + SQLModel**. The single source of truth: auth, data,
  scoring, and all third-party integrations.
- `web/` — **React + Vite + TypeScript** dashboard (post-practice reflection).
- `extension/` — **Chrome Manifest V3** extension (live coaching over Slides).

Data flow: extension captures speech → backend transcribes (ElevenLabs) and
coaches (Gemini, with Backboard memory) → live tips to the extension, summary +
score + leaderboard to the web app; runs synced to TigerTable.

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

| Task | File(s) |
| --- | --- |
| Add/modify an API endpoint | `backend/app/routers/*.py` (+ register in `app/main.py`) |
| Change the data model | `backend/app/models.py` (+ `schemas.py` for the API contract) |
| Edit AI coaching behavior | `backend/app/services/gemini.py` (prompts live here) |
| Transcription | `backend/app/services/elevenlabs.py` |
| Memory across runs | `backend/app/services/backboard.py` |
| Analytics sync | `backend/app/services/tigertable.py` |
| Leaderboard/score math | `backend/app/services/scoring.py` |
| Web pages | `web/src/pages/*.tsx`, API client in `web/src/api.ts` |
| Live overlay / speech capture | `extension/src/content.js` |
| Extension network + auth | `extension/src/background.js` (service worker) |

## Conventions

- **Backend:** async route handlers; DB access via the `get_session` dependency;
  auth via the `get_current_user` dependency. Keep third-party calls inside
  `services/` — routers should not call `httpx`/SDKs directly.
- **Every integration must keep its no-key stub fallback.** Don't break local dev.
- **Web:** functional components + hooks; all HTTP goes through `web/src/api.ts`.
  No secrets in the frontend.
- **Extension:** content scripts stay thin and talk to the backend only via
  `chrome.runtime.sendMessage` to the service worker (single token owner).
- **Secrets:** never commit real keys. Only `.env.example` is tracked.

## Common tasks

- **New domain** (beyond tech/law/finance/marketing): extend the `Domain` enum in
  `backend/app/models.py`, then update the `DOMAINS` arrays in the web pages and
  the extension popup `<select>`.
- **New feedback signal**: add to the Gemini prompt in `services/gemini.py` and,
  if persisted, extend the `Feedback` model + `FeedbackPublic` schema.

## Guardrails

- Ask before adding heavy dependencies or new services.
- Keep changes minimal and localized; match existing style.
- This is Windows/PowerShell — chain shell commands with `;`, not `&&`.
- Don't commit `heard.db`, `node_modules/`, `dist/`, or any `.env`.
