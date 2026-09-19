# Task 12 — Stretch: LinkedIn OAuth via Auth0

**Status:** stretch — after 10PM  
**Owner:** backend/app/dependencies.py + web/ auth flow

---

## Goal

Replace Supabase magic link with LinkedIn OAuth so users get their real name, avatar, and career context auto-populated.

---

## Flow

```
User clicks "Login with LinkedIn"
→ Auth0 handles LinkedIn OAuth
→ Auth0 issues JWT with linkedin_id, name, avatar, email
→ Frontend attaches JWT as Bearer token
→ Backend decodes Auth0 JWT (different secret/JWKS than Supabase)
→ Upsert User row with linkedin_id populated
```

---

## What changes

### Backend (`dependencies.py`)
- Verify Auth0 JWT via JWKS endpoint instead of Supabase HS256 secret
- `AUTH0_DOMAIN` env var → `https://{domain}/.well-known/jwks.json`
- `AUTH0_AUDIENCE` env var

### Frontend (`web/src/api.ts`)
- Replace `supabase.auth.signInWithOtp` with Auth0 React SDK login redirect
- `VITE_AUTH0_DOMAIN` + `VITE_AUTH0_CLIENT_ID` env vars on Vercel

### New env vars
```
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://api.heard.app
VITE_AUTH0_DOMAIN=your-tenant.auth0.com
VITE_AUTH0_CLIENT_ID=<public, safe to expose>
```

---

## Auth0 setup
1. Create application: Regular Web App (for callback) + SPA (for frontend)
2. Enable LinkedIn social connection in Auth0 dashboard
3. Add callback URLs: `http://localhost:5173, https://your-project.vercel.app`
4. Copy domain + client ID into env vars above

---

## Keep stub fallback
Current Supabase auth stays working if `AUTH0_DOMAIN` is not set — don't break local dev.
