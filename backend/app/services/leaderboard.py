"""Channel leaderboard + recommended peers.

Ranking rewards IMPROVEMENT (improvement_percent), not raw talent, so speakers
who started weak but grew rank highly. Only users with >= 2 completed sessions
in the channel are eligible. Private profiles are excluded. Ties break
deterministically (completed_sessions desc, then user_id asc).
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models import (
    TrainingSession, SessionFeedback, Profile, SESSION_COMPLETED,
)
from app.services import channels as channels_svc, progress as progress_svc


def _ranked_entries(channel_id: str, session: Session) -> list[dict]:
    """All eligible users in the channel, ranked by improvement_percent desc."""
    # Distinct users with completed sessions in this channel.
    user_ids = set(session.exec(
        select(TrainingSession.user_id).where(
            TrainingSession.channel_id == channel_id,
            TrainingSession.status == SESSION_COMPLETED,
        )
    ).all())

    entries = []
    for uid in user_ids:
        profile = session.get(Profile, uid)
        if not profile or profile.is_private:
            continue
        summary = progress_svc.improvement_for_user(uid, channel_id, session)
        if summary["completed_session_count"] < progress_svc.MIN_SESSIONS_FOR_IMPROVEMENT:
            continue
        if summary["improvement_percent"] is None:
            continue
        entries.append({
            "user_id": uid,
            "username": profile.username,
            "display_name": profile.display_name,
            "avatar_url": profile.avatar_url,
            "improvement_percent": summary["improvement_percent"],
            "completed_sessions": summary["completed_session_count"],
        })

    entries.sort(
        key=lambda e: (-e["improvement_percent"], -e["completed_sessions"], e["user_id"])
    )
    for i, e in enumerate(entries, start=1):
        e["rank"] = i
    return entries


def channel_leaderboard(
    channel_id: str, session: Session, *,
    viewer_id: Optional[str] = None, limit: int = 20, offset: int = 0,
) -> dict:
    channel = channels_svc.get_channel(channel_id, session)
    entries = _ranked_entries(channel.id, session)

    page = entries[offset:offset + limit]
    viewer_rank = None
    if viewer_id:
        for e in entries:
            if e["user_id"] == viewer_id:
                viewer_rank = e
                break

    return {
        "channel_id": channel.id,
        "total": len(entries),
        "entries": page,
        "viewer_rank": viewer_rank,
    }


def recommended_peers(channel_id: str, user_id: str, session: Session, *, limit: int = 3) -> list[dict]:
    """Top eligible leaderboard users in the channel, excluding the current user."""
    channel = channels_svc.get_channel(channel_id, session)
    entries = _ranked_entries(channel.id, session)
    peers = [e for e in entries if e["user_id"] != user_id]
    return peers[:limit]
