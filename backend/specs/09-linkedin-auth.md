# Spec 09 — LinkedIn OAuth via Auth0

**Depends on:** specs 01-04 (auth + routes live), Supabase user table  
**Touches:** `dependencies.py`, `models.py`, `requirements.txt`, `web/src/` (auth flow only), `.env.example`  
**Stretch prerequisite:** Auth0 account + LinkedIn app credentials

---

## Goal

Replace Supabase magic-link JWT with Auth0-issued JWTs so users sign in with LinkedIn. On first login, `name`, `avatar_url`, and `linkedin_id` are auto-populated from the LinkedIn profile — no manual entry needed.

---

## Auth0 setup (one-time, manual)

1. **Create Auth0 tenant** — auth0.com → create account → note `{domain}` (e.g. `dev-abc123.us.auth0.com`)
2. **Create SPA application** — Applications → Create → Single Page Application → copy `Client ID`
3. **Enable LinkedIn social connection** — Authentication → Social → LinkedIn → enable → add LinkedIn app credentials
4. **Set callback URLs** in Auth0 dashboard:
   ```
   Allowed Callback URLs:   http://localhost:5173, https://your-project.vercel.app
   Allowed Logout URLs:     http://localhost:5173, https://your-project.vercel.app
   Allowed Web Origins:     http://localhost:5173, https://your-project.vercel.app
   ```
5. **Create API** (for audience claim) — Applications → APIs → Create → identifier: `https://api.heard.app`

---

## JWT difference: Supabase vs Auth0

| | Supabase | Auth0 |
|---|---|---|
| Algorithm | HS256 (symmetric) | RS256 (asymmetric) |
| Secret | `SUPABASE_JWT_SECRET` (shared) | Public key from JWKS endpoint |
| `sub` claim | Supabase UUID | `linkedin\|{numeric_id}` |
| Extra claims | `email` | `name`, `picture`, `email` |
| Audience | none (verify_aud=False) | `https://api.heard.app` |

---

## New env vars

```
# Auth0
AUTH0_DOMAIN=dev-abc123.us.auth0.com
AUTH0_AUDIENCE=https://api.heard.app

# Frontend (safe to expose — public values only)
VITE_AUTH0_DOMAIN=dev-abc123.us.auth0.com
VITE_AUTH0_CLIENT_ID=<SPA client ID from Auth0 dashboard>
VITE_AUTH0_AUDIENCE=https://api.heard.app
```

Keep existing `SUPABASE_JWT_SECRET` — used as fallback when `AUTH0_DOMAIN` is not set.

---

## Backend — `dependencies.py`

Replace current HS256 decode with JWKS-based RS256 verification.

```python
import os
from functools import lru_cache
import httpx
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError

AUTH0_DOMAIN   = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "https://api.heard.app")


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    return httpx.get(url, timeout=5).json()


def _decode_auth0(token: str) -> dict:
    jwks = _get_jwks()
    unverified = jwt.get_unverified_header(token)
    key = next(k for k in jwks["keys"] if k["kid"] == unverified["kid"])
    return jwt.decode(
        token, key,
        algorithms=["RS256"],
        audience=AUTH0_AUDIENCE,
        issuer=f"https://{AUTH0_DOMAIN}/",
    )


def _decode_supabase(token: str) -> dict:
    return jwt.decode(
        token,
        os.getenv("SUPABASE_JWT_SECRET", ""),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401)
    try:
        # Use Auth0 if configured, fall back to Supabase
        if AUTH0_DOMAIN:
            payload = _decode_auth0(credentials.credentials)
        else:
            payload = _decode_supabase(credentials.credentials)
    except (JWTError, ExpiredSignatureError, StopIteration):
        raise HTTPException(status_code=401)

    sub   = payload.get("sub", "")
    email = payload.get("email", sub)
    name  = payload.get("name", email)
    pic   = payload.get("picture")

    # linkedin|123456 → store "123456" as linkedin_id
    linkedin_id = sub.split("|")[-1] if "|" in sub else sub

    user = session.exec(select(User).where(User.id == sub)).first()
    if not user:
        user = User(
            id=sub,
            linkedin_id=linkedin_id,
            name=name,
            avatar_url=pic,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    else:
        # refresh name/avatar on each login in case LinkedIn profile changed
        changed = False
        if name and user.name != name:
            user.name = name; changed = True
        if pic and user.avatar_url != pic:
            user.avatar_url = pic; changed = True
        if changed:
            session.add(user); session.commit(); session.refresh(user)

    return user
```

---

## New dependency — `python-jose[cryptography]`

Add to `requirements.txt`:
```
python-jose[cryptography]>=3.3.0
```

Remove `PyJWT` if it's the only JWT library currently used (check `requirements.txt`).

---

## Frontend — `web/src/` (auth flow only)

Install Auth0 React SDK:
```bash
cd web && npm install @auth0/auth0-react
```

### `web/src/main.tsx` — wrap app in Auth0Provider
```tsx
import { Auth0Provider } from "@auth0/auth0-react"

<Auth0Provider
  domain={import.meta.env.VITE_AUTH0_DOMAIN}
  clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
  authorizationParams={{
    redirect_uri: window.location.origin,
    audience: import.meta.env.VITE_AUTH0_AUDIENCE,
  }}
>
  <App />
</Auth0Provider>
```

### `web/src/api.ts` — swap token source
```ts
// Replace localStorage.getItem(TOKEN_KEY) with:
import { useAuth0 } from "@auth0/auth0-react"
// In components: const { getAccessTokenSilently } = useAuth0()
// token = await getAccessTokenSilently()
```

### `web/src/pages/Login.tsx` — replace email form
```tsx
import { useAuth0 } from "@auth0/auth0-react"
const { loginWithRedirect } = useAuth0()
<button onClick={() => loginWithRedirect()}>Sign in with LinkedIn</button>
```

---

## `.env.example` additions

```
# Auth0 (LinkedIn OAuth) — stretch feature
AUTH0_DOMAIN=
AUTH0_AUDIENCE=https://api.heard.app
VITE_AUTH0_DOMAIN=
VITE_AUTH0_CLIENT_ID=
VITE_AUTH0_AUDIENCE=https://api.heard.app
```

---

## Backwards compatibility

- If `AUTH0_DOMAIN` is **not set** → existing Supabase HS256 path runs unchanged. Local dev and tests continue to work with no changes.
- `_get_jwks()` is `@lru_cache` — JWKS is fetched once per process, not per request.
- Tests use `app.dependency_overrides[get_current_user]` — unaffected by this change.

---

## Test checklist

- [ ] `AUTH0_DOMAIN` unset → Supabase path still works (existing 59 tests pass unchanged)
- [ ] `AUTH0_DOMAIN` set → Auth0 RS256 path decodes valid token
- [ ] `name` + `avatar_url` populated on first login from LinkedIn claims
- [ ] `linkedin_id` stripped from `linkedin|{id}` sub claim
- [ ] `name` + `avatar_url` refreshed on subsequent logins if LinkedIn profile changed
- [ ] Expired Auth0 token → 401
- [ ] JWKS fetch failure → 401 (don't expose JWKS error to client)
- [ ] Wrong `kid` in token header → 401
