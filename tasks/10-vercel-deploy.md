# Task 10 — Vercel Deployment + Secrets

**Status:** todo  
**Owner:** web/ → Vercel; backend/ → Railway or Render

---

## Vercel is for the web frontend only

Vercel runs static/serverless JS. The FastAPI backend needs a container host — use **Railway** (free tier, Docker auto-detect) or **Render**.

---

## Web → Vercel (5 steps)

1. Push repo to GitHub (already done).
2. Go to vercel.com → New Project → Import `HackHers-2026/Heard`.
3. **Root Directory:** `web`
4. **Build Command:** `npm run build` (auto-detected from package.json)
5. **Output Directory:** `dist`

That's it — Vercel auto-deploys on every push to `main`.

---

## Secrets on Vercel (never in code)

In Vercel dashboard → Project → Settings → **Environment Variables**, add:

| Variable | Value | Notes |
|----------|-------|-------|
| `VITE_API_URL` | `https://your-backend.railway.app` | prod backend URL |
| `VITE_SUPABASE_URL` | `https://ytmrxkzczjsiorfcsbmc.supabase.co` | safe to expose |
| `VITE_SUPABASE_ANON_KEY` | `<anon key>` | safe to expose (anon, not service key) |

`VITE_*` variables are bundled into the client at build time — never put anything that must stay secret (service keys, JWT secrets, Gemini key) in a `VITE_` variable. Those live only in the backend's environment.

---

## Backend → Railway (5 steps)

1. railway.app → New Project → Deploy from GitHub → pick `backend/` as root.
2. Railway auto-detects Python and looks for `requirements.txt`.
3. Add a `Procfile` in `backend/`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set environment variables in Railway dashboard (same as `backend/.env`).
5. Copy the Railway public URL → paste into Vercel's `VITE_API_URL`.

---

## CORS

Add the Vercel domain to CORS origins in `backend/app/main.py`:
```python
origins = [
    "http://localhost:5173",
    "https://your-project.vercel.app",
]
```

---

## `.env` never commits — reminder

`.gitignore` already blocks `backend/.env`. Secrets flow:
```
Local dev   → backend/.env  (never committed)
Prod        → Railway env vars dashboard
Frontend    → Vercel env vars dashboard (VITE_ prefix, non-secret only)
```
