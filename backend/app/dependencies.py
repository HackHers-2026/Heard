import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlmodel import Session, select
from typing import Optional

from app.database import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            os.getenv("SUPABASE_JWT_SECRET", ""),
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        sub = payload.get("sub")
        email = payload.get("email", sub)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = session.exec(select(User).where(User.id == sub)).first()
    if not user:
        user = User(id=sub, linkedin_id=sub, name=email or "user")
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
