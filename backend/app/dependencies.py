import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlmodel import Session, select
from typing import Optional

from app.database import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Decode a Supabase HS256 JWT. Raises JWTError if invalid."""
    return jwt.decode(
        token,
        os.getenv("SUPABASE_JWT_SECRET", ""),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )


def upsert_user_from_payload(payload: dict, session: Session) -> User:
    """Get or create the User described by a decoded JWT payload."""
    sub = payload.get("sub")
    email = payload.get("email", sub)
    user = session.exec(select(User).where(User.id == sub)).first()
    if not user:
        user = User(id=sub, linkedin_id=sub, name=email or "user")
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
    try:
        payload = _decode_token(token)
    except JWTError:
        return None
    if not payload.get("sub"):
        return None
    return upsert_user_from_payload(payload, session)


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
