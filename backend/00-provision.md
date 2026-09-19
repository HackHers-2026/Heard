# Task 00 — Research & Provision

**Status as of 2026-09-18:** Supabase provisioned, tables live. Gemini key needed. Others are stub/stretch.

---

## MCP & tools setup

| Tool | Purpose | Status |
|------|---------|--------|
| Supabase MCP | Create tables, run migrations, query DB | **installed** — OAuth auth via `/mcp` → authenticate |
| ElevenLabs MCP | Test ElevenLabs APIs | not needed — stub fallback in place |
| Gemini MCP | n/a | not available — API key in code only |
| TigerTable MCP | Analytics pipeline | stretch only (after 10PM) |
| Backboard MCP | Gemini session memory | stretch only, wire after core Gemini works |

> Load Supabase tools via ToolSearch: `select:mcp__supabase__execute_sql` (or similar) after MCP authenticates.

---

## Services to provision

### 1. Supabase ✅
- Project ref: `ytmrxkzczjsiorfcsbmc`
- URL: `https://ytmrxkzczjsiorfcsbmc.supabase.co`
- [x] Project created
- [x] All 7 tables migrated (`001_initial_schema.sql` applied)
- [x] Supabase MCP installed
- [ ] **TODO:** Copy `SUPABASE_SERVICE_KEY` into `backend/.env` → Dashboard → Settings → API → service_role key
- [ ] **TODO:** Copy `SUPABASE_JWT_SECRET` into `backend/.env` → Dashboard → Settings → API → JWT Secret
- [ ] **TODO:** Set `DATABASE_URL` to Postgres URI for prod → Dashboard → Settings → Database → Connection string
- Free tier: 500 MB DB, 1 GB storage, 50k MAU — sufficient for hackathon

### 2. Gemini API ⬜
- Docs: https://ai.google.dev/gemini-api/docs
- [ ] Get API key from Google AI Studio (free tier: gemini-1.5-flash, 15 req/min)
- [ ] Copy `GEMINI_API_KEY` into `backend/.env`
- Rate limits: 15 RPM free — sufficient (we make ~3 calls per session)
- Model: `gemini-1.5-flash` (free tier) ✓ already set in config.py

### 3. ElevenLabs ⬜ (hold)
- **Decision: hold** — Web Speech API in extension is free with no quota. Wire ElevenLabs only if transcription quality is insufficient.
- If needed: copy `ELEVENLABS_API_KEY` into `.env`

### 4. TigerTable ⏭ (stretch, after 10PM)
- Skip unless time allows after 10PM

### 5. Backboard ⏭ (stretch)
- Wire after core Gemini calls work in spec 05
- If needed: copy `BACKBOARD_API_KEY` into `.env`

---

## Decision log

| Service | Free tier | Decision | Notes |
|---------|-----------|----------|-------|
| Supabase | 500 MB DB, 50k MAU | ✅ provisioned | tables live |
| Gemini | 15 RPM, gemini-1.5-flash | provision — get key | needed for all AI features |
| ElevenLabs | 10k chars/mo free | hold | Web Speech API sufficient for POC |
| TigerTable | unknown | stretch (after 10PM) | skip for now |
| Backboard | unknown | stretch | wire after core Gemini works |

---

## `backend/.env` — what to fill in

Copy `.env.example` to `.env`, then fill in:

```
SUPABASE_URL=https://ytmrxkzczjsiorfcsbmc.supabase.co
SUPABASE_SERVICE_KEY=<from Dashboard → Settings → API → service_role>
SUPABASE_JWT_SECRET=<from Dashboard → Settings → API → JWT Secret>
GEMINI_API_KEY=<from aistudio.google.com>
DATABASE_URL=sqlite:///./heard.db   # keep for local; swap to postgres URI for prod
```
