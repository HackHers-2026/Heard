"""Per-user, per-channel performance memory.

A compact rollup derived from completed sessions (NOT a replacement for raw
history). Updated after each successful completion so pre-/post-training AI calls
can quickly understand the user's channel-specific trajectory.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    UserChannelPerformanceProfile, SessionFeedback, TrainingSession, SESSION_COMPLETED,
)
from app.services import progress as progress_svc

STRENGTH_THRESHOLD = 75.0
WEAKNESS_THRESHOLD = 60.0


def get_profile(user_id: str, channel_id: str, session: Session) -> Optional[UserChannelPerformanceProfile]:
    return session.exec(
        select(UserChannelPerformanceProfile).where(
            UserChannelPerformanceProfile.user_id == user_id,
            UserChannelPerformanceProfile.channel_id == channel_id,
        )
    ).first()


def update_after_session(user_id: str, channel_id: str, session: Session) -> UserChannelPerformanceProfile:
    """Recompute and upsert the channel performance profile."""
    prog = progress_svc.channel_progress(user_id, channel_id, session)
    trends = prog.get("dimension_trends", {})

    strengths = [d for d, t in trends.items()
                 if t.get("recent") is not None and t["recent"] >= STRENGTH_THRESHOLD]
    weaknesses = [d for d, t in trends.items()
                  if t.get("recent") is not None and t["recent"] < WEAKNESS_THRESHOLD]

    latest_fb = _latest_feedback(user_id, channel_id, session)
    recent_patterns, goals = [], []
    if latest_fb:
        recent_patterns = [
            p.get("pattern") for p in (latest_fb.persistent_patterns or []) if p.get("pattern")
        ] + [
            p.get("pattern") for p in (latest_fb.new_patterns or []) if p.get("pattern")
        ]
        goals = [g.get("goal") for g in (latest_fb.next_session_goals or []) if g.get("goal")]

    profile = get_profile(user_id, channel_id, session)
    if not profile:
        profile = UserChannelPerformanceProfile(user_id=user_id, channel_id=channel_id)

    profile.completed_sessions = prog.get("completed_session_count", 0)
    profile.baseline_score = prog.get("baseline_score")
    profile.recent_score = prog.get("recent_score")
    profile.improvement_percent = prog.get("improvement_percent")
    profile.dimension_trends = trends
    profile.recurring_strengths = strengths
    profile.recurring_weaknesses = weaknesses
    profile.recent_patterns = recent_patterns[:6]
    profile.current_training_goals = goals[:3]
    profile.updated_at = datetime.utcnow().isoformat()

    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _latest_feedback(user_id: str, channel_id: str, session: Session) -> Optional[SessionFeedback]:
    row = session.exec(
        select(SessionFeedback)
        .join(TrainingSession, SessionFeedback.session_id == TrainingSession.id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.channel_id == channel_id,
            TrainingSession.status == SESSION_COMPLETED,
        )
        .order_by(TrainingSession.created_at.desc())
    ).first()
    return row


def serialize(profile: UserChannelPerformanceProfile) -> dict:
    return {
        "user_id": profile.user_id,
        "channel_id": profile.channel_id,
        "completed_sessions": profile.completed_sessions,
        "baseline_score": profile.baseline_score,
        "recent_score": profile.recent_score,
        "improvement_percent": profile.improvement_percent,
        "dimension_trends": profile.dimension_trends or {},
        "recurring_strengths": profile.recurring_strengths or [],
        "recurring_weaknesses": profile.recurring_weaknesses or [],
        "recent_patterns": profile.recent_patterns or [],
        "current_training_goals": profile.current_training_goals or [],
        "updated_at": profile.updated_at,
    }
