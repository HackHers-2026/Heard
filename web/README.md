# Heard — Web App (React + Vite + TypeScript)

The dashboard frontend: review past practices, read the AI "chat" for each run,
see your score + summary, climb the per-domain leaderboard, and DM mentors.

## Run

```bash
cd web
npm install
npm run dev   # http://localhost:5173
```

Requires the backend running on `http://localhost:8000` (the dev server proxies
`/api/*` there — see `vite.config.ts`).

## Pages
- `Login` — signup/login (JWT stored in localStorage)
- `Dashboard` — start runs, list practices
- `SessionChat` — transcript + AI feedback as a chat, generate final score
- `PreTraining` — domain-specific coaching before you start
- `Leaderboard` — ranked by improvement score + recommended mentors
- `Messages` — DM mentors for advice
