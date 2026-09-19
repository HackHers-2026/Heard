"""Profile helpers — the public identity behind each authenticated user.

``Profile.id`` == the Supabase auth user id. A profile row is created the first
time we see a user (on signup or first authenticated request), so channels,
leaderboards and DMs always have a display name / username / avatar to show.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import Profile


def _slug_username(seed: str) -> str:
    base = "".join(c for c in (seed or "user").lower() if c.isalnum()) or "user"
    return base[:20]


def ensure_profile(
    user_id: str,
    session: Session,
    *,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> Profile:
    """Get-or-create the profile row for a user. Idempotent."""
    profile = session.get(Profile, user_id)
    if profile:
        return profile

    seed = (email.split("@")[0] if email else None) or display_name or user_id[:8]
    username = _unique_username(_slug_username(seed), session)
    profile = Profile(
        id=user_id,
        display_name=display_name or (email.split("@")[0] if email else "New speaker"),
        username=username,
        avatar_url=avatar_url,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _unique_username(base: str, session: Session) -> str:
    candidate = base
    n = 1
    while session.exec(select(Profile).where(Profile.username == candidate)).first():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def update_profile(user_id: str, session: Session, **fields) -> Profile:
    profile = ensure_profile(user_id, session)
    allowed = {"display_name", "username", "avatar_url", "bio", "is_private"}
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(profile, key, value)
    profile.updated_at = datetime.utcnow().isoformat()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def serialize_profile(profile: Profile, *, public: bool = False) -> dict:
    data = {
        "id": profile.id,
        "display_name": profile.display_name,
        "username": profile.username,
        "avatar_url": profile.avatar_url,
    }
    if not public:
        data.update({
            "bio": profile.bio,
            "is_private": profile.is_private,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        })
    return data


def public_profile(user_id: str, session: Session) -> Optional[dict]:
    profile = session.get(Profile, user_id)
    return serialize_profile(profile, public=True) if profile else None
