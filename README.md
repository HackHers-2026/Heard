# Heard

Women have brilliant ideas. Too often, they go unspoken.

**Heard** is a tool that helps women practice speaking up — with encouragement
before they start, real-time coaching while they speak, and a community to
grow with after.

> Built for the **developHer** track @ Hackhers 2026 — empowering women through
> education, career growth, and meaningful connections.

## Why

- **75%** of female executives report imposter syndrome (KPMG Women's Leadership Study).
- **29%** of women regularly hold back in meetings; **47%** cite low confidence and **52%** a harsh inner critic (Women Rising).
- **45%** of female leaders find it hard to speak up in virtual meetings (Catalyst).
- Men speak **~75%** of the time in decision-making meetings (*The Silent Sex*, Princeton/BYU).

Heard gives women a private, judgment-free place to practice and improve — and a
community that lifts each other up.

## How it works

```
                 ┌──────────────────────────┐
   Google Slides │  Chrome Extension (UI 1)  │  live pop-up tips
   practice  ──▶ │  captures speech          │ ◀────────────────┐
                 └────────────┬─────────────┘                   │
                              │ transcript chunks               │
                              ▼                                  │
                 ┌──────────────────────────┐   ElevenLabs (STT)│
                 │      FastAPI Backend      │──▶ Gemini (coach) ─┘
                 │  auth · sessions · score  │──▶ Backboard (memory)
                 │  leaderboard · DMs        │──▶ TigerTable (analytics)
                 └────────────┬─────────────┘
                              │ transcripts, scores, summaries
                              ▼
                 ┌──────────────────────────┐
                 │     Web App (UI 2)        │  chat-style AI feedback,
                 │  dashboard · leaderboard  │  scores, mentors, DMs
                 └──────────────────────────┘
```

Two frontends, one backend:

1. **Chrome extension** — overlays Google Slides, captures your pitch, and shows
   live Gemini coaching pop-ups.
2. **Web app** — the AI feedback shows up as a text chat with a summary + score,
   plus a per-domain leaderboard and DMs with mentors.

**Phases:** _pre-training_ (domain-specific prep coaching) → _live feedback_
(extension pop-ups) → _post-training_ (transcript export, scoring, improvement
tracking over time).

## Tech

| Layer | Tech |
| --- | --- |
| Backend | Python · FastAPI · SQLModel (SQLite → Postgres) |
| Web app | React · Vite · TypeScript |
| Extension | Chrome Manifest V3 |
| Transcription | ElevenLabs (Scribe STT) |
| Coaching AI | Google Gemini |
| Memory | Backboard |
| Analytics | TigerTable |

> Everything runs **without API keys** thanks to built-in stubs — wire real keys
> in when you're ready.

## Quick start

```bash
# 1. Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload

# 2. Web app (new terminal)
cd web
npm install && npm run dev

# 3. Extension
# chrome://extensions → Developer mode → Load unpacked → select extension/
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design and each
folder's README for details.

## Repo layout

```
Heard/
├── backend/     FastAPI API (one backend, two frontends)
├── web/         React + Vite web app
├── extension/   Chrome MV3 extension
├── docs/        Architecture + notes
└── CLAUDE.md    Guide for AI coding agents
```
