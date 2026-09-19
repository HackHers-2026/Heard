"""Channel-specific improvement / progress calculation.

Improvement is always scoped to a single channel — a user's Finance sessions
never mix with their Technology sessions. Kept here (not duplicated) so the
leaderboard and the progress endpoint share one definition.
"""
from __future__ import annotations

from statistics import mean
from typing import Optional

from sqlmodel import Session, select

from app.models import TrainingSession, SessionFeedback, SESSION_COMPLETED
from app.services import analysis, channels as channels_svc

RECENT_WINDOW = 3
MIN_SESSIONS_FOR_IMPROVEMENT = 2
_DIMENSIONS = ["clarity", "conciseness", "pace", "volume", "confidence", "structure"]


def compute_improvement(overall_scores: list[float]) -> dict:
    """Given completed overall scores in chronological order, compute improvement.

    baseline = first completed score
    recent   = mean of up to the 3 most recent scores
    improvement_percent = ((recent - baseline) / max(baseline, 1)) * 100
                          (None until there are >= 2 completed sessions)
    Negative improvement is NOT clamped.
    """
    count = len(overall_scores)
    if count == 0:
        return {"baseline_score": None, "recent_score": None,
                "improvement_percent": None, "completed_session_count": 0}

    baseline = overall_scores[0]
    recent = round(mean(overall_scores[-RECENT_WINDOW:]), 2)
    improvement = None
    if count >= MIN_SESSIONS_FOR_IMPROVEMENT:
        improvement = round(((recent - baseline) / max(baseline, 1)) * 100, 2)

    return {
        "baseline_score": round(baseline, 2),
        "recent_score": recent,
        "improvement_percent": improvement,
        "completed_session_count": count,
    }


def _completed_feedback(user_id: str, channel_id: str, session: Session) -> list[SessionFeedback]:
    """Completed sessions' feedback (with non-null overall), chronological."""
    rows = session.exec(
        select(SessionFeedback, TrainingSession)
        .join(TrainingSession, SessionFeedback.session_id == TrainingSession.id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.channel_id == channel_id,
            TrainingSession.status == SESSION_COMPLETED,
        )
        .order_by(TrainingSession.created_at)
    ).all()
    return [fb for fb, _ in rows if fb.overall_score is not None]


def channel_progress(user_id: str, channel_id: str, session: Session) -> dict:
    channel = channels_svc.get_channel(channel_id, session)
    feedbacks = _completed_feedback(user_id, channel.id, session)
    overall = [fb.overall_score for fb in feedbacks]
    result = compute_improvement(overall)

    result["channel_id"] = channel.id
    result["completed_sessions"] = result["completed_session_count"]
    result["dimension_trends"] = _dimension_trends(feedbacks)
    return result


def _dimension_trends(feedbacks: list[SessionFeedback]) -> dict:
    trends: dict = {}
    for dim in _DIMENSIONS:
        vals = [getattr(fb, f"{dim}_score") for fb in feedbacks
                if getattr(fb, f"{dim}_score") is not None]
        if not vals:
            trends[dim] = {"baseline": None, "recent": None, "delta": None}
            continue
        baseline = vals[0]
        recent = round(mean(vals[-RECENT_WINDOW:]), 2)
        trends[dim] = {
            "baseline": round(baseline, 2),
            "recent": recent,
            "delta": round(recent - baseline, 2),
        }
    return trends


def improvement_for_user(user_id: str, channel_id: str, session: Session) -> dict:
    """Bare improvement summary for leaderboard ranking."""
    feedbacks = _completed_feedback(user_id, channel_id, session)
    return compute_improvement([fb.overall_score for fb in feedbacks])
