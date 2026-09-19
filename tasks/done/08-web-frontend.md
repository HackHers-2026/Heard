# Task 08 — Web Frontend (React + Vite + TypeScript)

**Status:** todo  
**Owner:** web/  
**Reads:** docs/contracts.md, backend/README.md

---

## Goal

Build the React dashboard covering all 5 product flows. All HTTP goes through `web/src/api.ts`. No secrets in frontend.

---

## Pages to implement

| Page | Route | Flow |
|------|-------|------|
| Login | `/` | Supabase magic link → redirect to Dashboard |
| Dashboard | `/dashboard` | Pre-speech encouragement button + recent speeches |
| PreTraining | `/pre-training` | "Encourage me" form (mode: quick / plan) |
| SessionChat | `/session` | Live nudge display — polls or receives nudge from extension |
| Leaderboard | `/leaderboard` | Community feed (paginated, filter by career_tag, like toggle) |
| Messages | `/messages` | Mentor DM thread list + inbox |
| Profile | `/profile/:id` | Radar chart (5 metrics), mentor toggle, speech history |

---

## Key components

- **RadarChart** — recharts or Chart.js, 5 axes: clarity/volume/pace/confidence/structure
- **NudgeOverlay** — floating card shown during live session
- **SpeechCard** — score summary + "View Report" link
- **PostCard** — community post with like button
- **MentorCard** — mentor suggestion from `/api/mentor/suggest`

---

## api.ts contract

All calls hit `VITE_API_URL` (env var, default `http://localhost:8000`). Attach `Authorization: Bearer <supabase_access_token>` from `supabase.auth.getSession()` on every authenticated call.

```ts
export const api = {
  encourage: (mode, context?) => POST /api/encourage
  speechStart: () => POST /api/speech/start
  speechSegment: (body) => POST /api/speech/segment
  speechEnd: (speech_id) => POST /api/speech/end
  report: (speech_id) => GET /api/speech/:id/report
  feed: (cursor?, career_tag?) => GET /api/feed
  like: (post_id) => POST /api/feed/:id/like
  profile: (user_id) => GET /api/profile/:id
  mentorConnect: (mentor_id, speech_id) => POST /api/mentor/connect
}
```

---

## Auth flow

1. User lands on `/`, enters email → `supabase.auth.signInWithOtp({ email })`
2. Magic link redirects back → `supabase.auth.onAuthStateChange` fires → store session
3. All subsequent API calls attach the JWT as Bearer token

---

## Environment

```
VITE_API_URL=http://localhost:8000     # dev; set to prod URL on Vercel
VITE_SUPABASE_URL=https://ytmrxkzczjsiorfcsbmc.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key from Dashboard>
```

Never put `SERVICE_KEY` or `JWT_SECRET` in frontend — those are backend-only.
