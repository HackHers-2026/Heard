"""Auth + profile endpoints (Supabase-backed)."""
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user, bearer
from app.errors import APIError
from app.services import supabase_auth, profiles

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_private: Optional[bool] = None


@router.post("/signup")
def signup(body: SignupRequest, session: Session = Depends(get_session)):
    result = supabase_auth.signup(body.email, body.password, body.display_name)
    user = result.get("user") or {}
    if user.get("id"):
        profiles.ensure_profile(
            user["id"], session,
            display_name=body.display_name, email=body.email,
        )
    return result


@router.post("/login")
def login(body: LoginRequest):
    return supabase_auth.login(body.email, body.password)


@router.post("/logout")
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    user=Depends(get_current_user),
):
    if credentials:
        supabase_auth.logout(credentials.credentials)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user), session: Session = Depends(get_session)):
    profile = profiles.ensure_profile(user.id, session, display_name=user.name)
    return {"user": {"id": user.id, "name": user.name}, "profile": profiles.serialize_profile(profile)}


@router.patch("/profile")
def update_profile(
    body: ProfileUpdateRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = profiles.update_profile(user.id, session, **body.model_dump(exclude_none=True))
    return {"profile": profiles.serialize_profile(profile)}


@router.get("/profile/{user_id}")
def get_public_profile(
    user_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    data = profiles.public_profile(user_id, session)
    if not data:
        raise APIError(404, "USER_NOT_FOUND", "Profile was not found.")
    return {"profile": data}
