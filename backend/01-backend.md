# Backend — Index

**Stack:** FastAPI + SQLModel · SQLite (dev) → Postgres (prod) · Gemini · ElevenLabs · Backboard · TigerTable (stretch)

Read `docs/contracts.md` first, then work through specs in order.

## Specs

| File | What it covers | Unit tests | Session tip |
|------|---------------|------------|-------------|
| `specs/01-setup.md` | FastAPI scaffold, deps, health check | `test_setup.py` | no MCP needed |
| `specs/02-db.md` | SQLModel models + Supabase migration | `test_db.py` | load Supabase MCP |
| `specs/03-auth.md` | Magic link JWT validation, user upsert | `test_auth.py` | no MCP needed |
| `specs/04-routes.md` | All 9 API routes (stubs ok) | `test_routes.py` | no MCP needed |
| `specs/05-gemini.md` | 3 Gemini calls + prompts + Backboard | `test_gemini.py` | load Backboard MCP |
| `specs/06-scoring.md` | 5-metric scoring + mentor matching | `test_scoring.py` | no MCP needed |
| `specs/07-component-test.md` | Full backend happy path | `test_component.py` | no MCP needed |

## Build order
01 → 02 → 03 → 04 → 05 → 06

Each spec is self-contained: open a fresh session with `CLAUDE.md` + `docs/contracts.md` + the spec file.

## Provision first
See `00-provision.md` — get all API keys into `backend/.env` before starting.
