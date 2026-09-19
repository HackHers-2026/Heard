"""Auth: validate Supabase access tokens via the Supabase Auth server.

We call `GET {SUPABASE_URL}/auth/v1/user` with the user's bearer token. This is
Supabase's supported way to verify a token and works with the current
asymmetric signing keys — no legacy shared `SUPABASE_JWT_SECRET` required.

Env:
    SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
"""
from typing import Optional

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def _fetch_supabase_user(token: str) -> Optional[dict]:
    """Return the Supabase user object for a token, or None if invalid.

    Validates the token against the Supabase Auth server. Returns None on any
    failure (missing config, network error, non-200) so callers can 401 or fall
    back as appropriate.
    """
    if not settings.supabase_url or not token:
        return None
    try:
        resp = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_publishable_key,
            },
            timeout=5,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


def upsert_user_from_supabase(su: dict, session: Session) -> User:
    """Get or create the local User row for a validated Supabase user."""
    sub = su.get("id")
    email = su.get("email")
    meta = su.get("user_metadata") or {}
    name = meta.get("display_name") or meta.get("name") or email or "user"

    user = session.exec(select(User).where(User.id == sub)).first()
    if not user:
        user = User(id=sub, linkedin_id=sub, name=name)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def authenticate_token(token: Optional[str], session: Session) -> Optional[User]:
    """Validate a raw bearer token and upsert the user.

    Returns the User on success, or None if the token is missing/invalid.
    Usable outside the HTTP dependency system — e.g. from the /ws/stt
    WebSocket, where browsers can't send an Authorization header.
    """
    if not token:
        return None
    su = _fetch_supabase_user(token)
    if not su or not su.get("id"):
        return None
    return upsert_user_from_supabase(su, session)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = authenticate_token(credentials.credentials, session)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
