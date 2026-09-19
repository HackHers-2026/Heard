# Heard web app

React, Vite, and TypeScript frontend for Heard’s communication-training workspace.

## Run locally

```bash
cd web
npm install
npm run dev
```

The Vite development server proxies `/api/*` to `http://localhost:8000`. Set
`VITE_API_BASE_URL` when the FastAPI service is hosted elsewhere.

Copy `.env.example` to `.env.local` and provide the same Supabase project used
by the backend:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_API_BASE_URL` (optional)

## Routes

- `/pre-training/:channelId?/:threadId?`
- `/post-training/:channelId?/:sessionId?`
- `/leaderboard/:channelId?`
- `/dms/:conversationId?`

All channel, session, leaderboard, peer, and message content is loaded from the
FastAPI backend. The browser never calls an AI provider directly.
