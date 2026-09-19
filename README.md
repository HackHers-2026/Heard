# Heard

Women have brilliant ideas. Too often, they go unspoken.

**Heard** is an adaptive communication coach that helps women practice speaking
up — with encouragement before they start, real-time coaching while they speak,
and a personal coach that *remembers them* and grows with them over time.

> Built for the **developHer** track @ Hackhers 2026 — empowering women through
> education, career growth, and meaningful connections.

## Why

- **75%** of female executives report imposter syndrome (KPMG Women's Leadership Study).
- **29%** of women regularly hold back in meetings; **47%** cite low confidence and **52%** a harsh inner critic (Women Rising).
- **45%** of female leaders find it hard to speak up in virtual meetings (Catalyst).
- Men speak **~75%** of the time in decision-making meetings (*The Silent Sex*, Princeton/BYU).

Most tools stop at *"AI grades your speech."* Heard doesn't. It builds a
**longitudinal speaking profile** for each woman, so every session starts from
where she left off — not from zero.

---

## The core idea: Backboard as a stateful coaching brain

Heard is centered on **[Backboard](https://docs.backboard.io)** as a *stateful
memory assistant* wrapped around Gemini. Backboard is **not** a decorative extra
API here — it is the persistent coaching layer that gives every user a coach who
remembers their recurring patterns, knows what they've already improved, and
focuses each intervention on their next highest-impact skill.

The mapping is the whole design:

```
                    ONE USER
                       │
                       ▼
              Backboard Assistant          ← the user's long-term coach
        persistent for this user forever     (memories live here)
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
     Session 1      Session 2      Session 3   ← one Backboard Thread each
      Thread A       Thread B       Thread C
         │
    ┌────┼────┐
    ▼    ▼    ▼
  Min 1 Min 2 Min 3                            ← one Message per 60s segment
```

| Backboard concept | Heard concept | Stored as |
|-------------------|---------------|-----------|
| **Assistant** | The user's long-term speaking coach (one per user) | `User.backboard_assistant_id` |
| **Thread** | One practice / presentation session | `Speech.backboard_thread_id` |
| **Message** | One 60-second transcript segment | `RealtimeSegment` |
| **Memory** | Durable communication patterns, goals, progress | Backboard (assistant-level) |

Because memories are stored at the **assistant level** and shared across that
assistant's threads, Thread B can draw on what the coach learned in Thread A.
Each user gets their **own** assistant so coaching memory is never mixed between
users.

Gemini stays the model that actually produces the coaching — we route through
Backboard with `llm_provider="google"` — while Backboard supplies the persistent
state, cross-session memory, and tool calling around it:

```
                    ┌── Backboard thread   (this session's ordered history)
  Transcript → Backboard ── Backboard memory (past sessions' patterns/goals)
                    └── Google / Gemini    (reasoning + structured feedback)
                              ↓
                           Feedback
```

### Memory is split into two modes — on purpose

We never fill long-term memory with transient per-minute noise.

```
  LIVE (during the session)          END OF SESSION
  memory="Readonly"                  memory="Auto"
  ↓                                  ↓
  RETRIEVE past coaching memories    EXTRACT durable coaching memories
  but DON'T write per-minute garbage from the completed session
```

So minute 3 is coached with **past coaching context + minutes 1 & 2 of this
thread + the current minute** — real personalization. When the session ends, one
`memory="Auto"` call lets Backboard extract durable, communication-specific
memories for next time (via a custom fact-extraction + update-memory prompt).

### Memory is grounded by a tool call

Memory is great for patterns (*"tends to bury the main claim"*), but not for
exact analytics. So the coach assistant has one function tool,
`get_recent_performance()`, which pulls precise recent scores from our database.
The coach can then say something genuinely useful:

> *"Your filler rate has improved substantially across recent sessions. Focus on
> transitions now rather than trying to fix everything at once."*

---

## The complete flow

```
USER SPEAKS
     │
     ▼
ElevenLabs Scribe v2  (realtime STT)
     │  committed transcripts
     ▼
SpeechSegmenter  ── buffers ~60s ──▶ RealtimeSegment  (speech_id, segment_index, transcript)
     │                                      │
     │  never blocks transcription          ▼
     └────────────────────────────▶ asyncio Queue ──▶ Coaching worker (ONE per session)
                                                              │
                                          ┌───────────────────┤
                                          │                   ▼
                            Backboard thread + memory   Google / Gemini
                                          └─────────┬─────────┘
                                                    ▼
                                     structured coaching feedback
                                     { focus_area, nudge, evidence,
                                       progress, next_minute_goal, scores }
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              ▼                                           ▼
                     SQLite (nudge + feedback_json)             WebSocket → Chrome sidebar
                                                                 "Lead with your main claim
                                                                  before the background."
```

**Why one queue worker per session?** So minute 1 → 2 → 3 always reach the
Backboard thread **in order**, even if one request is slower than another.
Transcription is never blocked while Gemini/Backboard think.

**What the sidebar shows vs. what we store:** the sidebar shows only the short
`nudge` (plus an optional expandable *"Why?"*). The full structured JSON —
focus area, evidence, progress, next-minute goal, and live scores — is saved to
`RealtimeSegment.feedback_json` for the post-session report.

The product framing this enables:

```
SESSION 1  "You spend too long on context before your main point."
              ↓ stored as coaching memory
SESSION 2  Min 1: "You stated your thesis earlier than last time. Keep that.
                   Now work on transitions."
           Min 2: "Transition improved. Make the next evidence more specific."
              ↓ session ends → Backboard updates the long-term profile
SESSION 3  The coach starts from where she left off, not from zero.
```

---

## Product surfaces

Two frontends, one backend:

1. **Chrome extension** — the *live* surface. Streams mic audio to the backend,
   which transcribes (ElevenLabs) and coaches (Backboard + Gemini), and shows
   real-time nudges in the side panel.
2. **Web app** — the *reflective* surface. Pre-speech encouragement, the
   post-speech report (5-metric score + summary + suggestions), community feed,
   mentor connections, and a profile radar chart.

**Phases:** _pre-training_ (prep coaching) → _live feedback_ (extension nudges,
Backboard-powered) → _post-training_ (report + longitudinal progress).

---

## Tech

| Layer | Tech |
| --- | --- |
| Backend | Python · FastAPI · SQLModel (SQLite → Postgres) |
| Web app | React · Vite · TypeScript |
| Extension | Chrome Manifest V3 (Web Speech + Web Audio API) |
| Transcription | ElevenLabs (Scribe v2 realtime STT) |
| **Coaching brain** | **Backboard** (stateful memory assistant) → **Google Gemini** |
| Analytics | TigerData (TimescaleDB) |

> **Runs without API keys.** Every external service — including Backboard — has a
> built-in stub fallback, so the whole pipeline runs end-to-end for local dev and
> demos. Wire real keys into `backend/.env` when you're ready.

### Backboard integration at a glance

| Piece | Where |
|-------|-------|
| Coaching service (assistant lifecycle, `coach_segment`, `finalize_session`, tool) | `backend/app/services/backboard.py` |
| Per-session queue worker (in-order, non-blocking) | `backend/app/services/coaching.py` |
| Segment buffering + `on_segment` hook | `backend/app/services/segmenter.py` |
| Realtime WebSocket wiring | `backend/app/routers/stt.py` |

Uses the official **`backboard-sdk`**. Choose the Gemini model Backboard routes
through via `BACKBOARD_GOOGLE_MODEL` (list current options with
`GET /models/provider/google`).

---

## Quick start

```bash
# 1. Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows (PowerShell)
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload                    # http://localhost:8000/docs

# 2. Web app (new terminal)
cd web
npm install && npm run dev                        # http://localhost:5173

# 3. Extension
# chrome://extensions → Developer mode → Load unpacked → select extension/
```

To enable adaptive coaching (optional — stubs work without it), add to
`backend/.env`:

```env
BACKBOARD_API_KEY=your_key          # Backboard Dashboard → Settings → API Keys
BACKBOARD_GOOGLE_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key             # only needed for encourage/score/chat flows
ELEVENLABS_API_KEY=your_key         # only needed for real transcription
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design and each
folder's README for details.

---

## Repo layout

```
Heard/
├── backend/     FastAPI API — auth, data, scoring, and the Backboard coaching brain
│   └── app/services/  backboard.py · coaching.py · segmenter.py · gemini.py · elevenlabs.py
├── web/         React + Vite web app
├── extension/   Chrome MV3 extension (live capture + coaching sidebar)
├── docs/        Architecture + data/API contracts
└── CLAUDE.md    Guide for AI coding agents
```
