"""AI context builder — assembles explicit, Supabase-sourced context packets.

Route handlers must NOT hand-assemble giant prompts. These functions gather the
user profile, channel, current session evidence, and CHANNEL-SPECIFIC history
(previous session, recent averages, baseline, recurring patterns, goals) into a
compact structured object for Backboard/Gemini.

Token efficiency (requirement 30):
  * current session  → full transcript + full metrics
  * previous session → scores + metric summary (+ transcript only if short)
  * older sessions   → structured summaries only
History is always CHANNEL-SPECIFIC (requirement 28).
"""
from __future__ import annotations

from statistics import mean
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    TrainingSession, TranscriptSegment, SessionFeedback, Channel,
    UserChannelPerformanceProfile, SESSION_COMPLETED,
)
from app.services import analysis, channels as channels_svc, progress as progress_svc

_DIMS = ["clarity", "conciseness", "pace", "volume", "confidence", "structure"]
_PREV_TRANSCRIPT_MAX_CHARS = 2000
_RECENT_WINDOW = 3


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _channel_dict(channel: Channel) -> dict:
    return {"id": channel.id, "slug": channel.slug, "name": channel.name}


def _scores(fb: SessionFeedback) -> dict:
    return {d: getattr(fb, f"{d}_score") for d in _DIMS} | {"overall": fb.overall_score}


def _completed(user_id: str, channel_id: str, session: Session) -> list[tuple[TrainingSession, SessionFeedback]]:
    rows = session.exec(
        select(TrainingSession, SessionFeedback)
        .join(SessionFeedback, SessionFeedback.session_id == TrainingSession.id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.channel_id == channel_id,
            TrainingSession.status == SESSION_COMPLETED,
        )
        .order_by(TrainingSession.created_at)
    ).all()
    return list(rows)


def _session_summary(ts: TrainingSession, fb: SessionFeedback, *, include_transcript: bool, session: Session) -> dict:
    summary = {
        "session_id": ts.id,
        "title": ts.title,
        "created_at": ts.created_at,
        "scores": _scores(fb),
        "metrics": {
            "average_wpm": fb.average_wpm,
            "filler_rate": fb.filler_rate,
            "filler_count": fb.filler_count,
            "volume_consistency": fb.volume_consistency,
        },
        "priority_moments": fb.priority_moments or [],
        "persistent_patterns": fb.persistent_patterns or [],
    }
    if include_transcript:
        segs = session.exec(
            select(TranscriptSegment)
            .where(TranscriptSegment.session_id == ts.id)
            .order_by(TranscriptSegment.segment_index)
        ).all()
        transcript = " ".join((s.transcript or "") for s in segs).strip()
        if transcript and len(transcript) <= _PREV_TRANSCRIPT_MAX_CHARS:
            summary["transcript"] = transcript
    return summary


def _recent_averages(history: list[tuple[TrainingSession, SessionFeedback]]) -> dict:
    window = history[-_RECENT_WINDOW:]
    out = {}
    for d in _DIMS:
        vals = [getattr(fb, f"{d}_score") for _, fb in window if getattr(fb, f"{d}_score") is not None]
        out[d] = round(mean(vals), 2) if vals else None
    overalls = [fb.overall_score for _, fb in window if fb.overall_score is not None]
    out["overall"] = round(mean(overalls), 2) if overalls else None
    return out


def _perf_profile_dict(user_id: str, channel_id: str, session: Session) -> Optional[dict]:
    p = session.exec(
        select(UserChannelPerformanceProfile).where(
            UserChannelPerformanceProfile.user_id == user_id,
            UserChannelPerformanceProfile.channel_id == channel_id,
        )
    ).first()
    if not p:
        return None
    return {
        "completed_sessions": p.completed_sessions,
        "baseline_score": p.baseline_score,
        "recent_score": p.recent_score,
        "improvement_percent": p.improvement_percent,
        "dimension_trends": p.dimension_trends or {},
        "recurring_strengths": p.recurring_strengths or [],
        "recurring_weaknesses": p.recurring_weaknesses or [],
        "recent_patterns": p.recent_patterns or [],
        "current_training_goals": p.current_training_goals or [],
    }


def _historical_block(user_id: str, channel_id: str, session: Session, *, exclude_session_id: Optional[str] = None) -> dict:
    history = [(ts, fb) for ts, fb in _completed(user_id, channel_id, session)
               if ts.id != exclude_session_id]
    if not history:
        return {"has_history": False}

    baseline_ts, baseline_fb = history[0]
    prev_ts, prev_fb = history[-1]
    return {
        "has_history": True,
        "session_count": len(history),
        "baseline": _session_summary(baseline_ts, baseline_fb, include_transcript=False, session=session),
        "baseline_overall_score": baseline_fb.overall_score,
        "previous_session": _session_summary(prev_ts, prev_fb, include_transcript=True, session=session),
        "previous_overall_score": prev_fb.overall_score,
        "previous_scores": _scores(prev_fb),
        "recent_averages": _recent_averages(history),
        "historical_overall_scores": [fb.overall_score for _, fb in history],
        "dimension_trends": progress_svc.channel_progress(user_id, channel_id, session).get("dimension_trends", {}),
        "recurring_observations": (_perf_profile_dict(user_id, channel_id, session) or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public builders
# ─────────────────────────────────────────────────────────────────────────────

def build_pretraining_context(user_id: str, channel_id: str, session: Session) -> dict:
    channel = channels_svc.get_channel(channel_id, session)
    history = _completed(user_id, channel.id, session)
    profile = _perf_profile_dict(user_id, channel.id, session)

    recent = [
        _session_summary(ts, fb, include_transcript=False, session=session)
        for ts, fb in history[-_RECENT_WINDOW:]
    ]
    return {
        "channel": _channel_dict(channel),
        "has_history": bool(history),
        "performance_profile": profile or {},
        "recent_sessions": recent,
        "previous_session": recent[-1] if recent else None,
        "baseline_overall_score": history[0][1].overall_score if history else None,
    }


def build_session_analysis_context(user_id: str, session_id: str, session: Session) -> dict:
    ts = session.get(TrainingSession, session_id)
    channel = session.get(Channel, ts.channel_id)
    segments = session.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.segment_index)
    ).all()

    evidence = analysis.session_evidence(list(segments))
    return {
        "channel": _channel_dict(channel) if channel else {"id": ts.channel_id},
        "current_session": {
            "session_id": ts.id,
            "title": ts.title,
            **evidence,
        },
        "historical": _historical_block(user_id, ts.channel_id, session, exclude_session_id=session_id),
    }


def build_posttraining_chat_context(user_id: str, session_id: str, session: Session) -> dict:
    ts = session.get(TrainingSession, session_id)
    channel = session.get(Channel, ts.channel_id)
    fb = session.exec(
        select(SessionFeedback).where(SessionFeedback.session_id == session_id)
    ).first()
    segs = session.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.segment_index)
    ).all()
    transcript = "\n".join(
        f"[{int(s.start_seconds)}s-{int(s.end_seconds)}s] {s.transcript}" for s in segs
    )

    feedback_block = None
    if fb:
        feedback_block = {
            "scores": _scores(fb),
            "summary": fb.summary,
            "priority_moments": fb.priority_moments or [],
            "strongest_moments": fb.strongest_moments or [],
            "next_session_goals": fb.next_session_goals or [],
            "metrics_interpretation": fb.metrics_interpretation or {},
        }

    return {
        "channel": _channel_dict(channel) if channel else {"id": ts.channel_id},
        "current_session": {
            "session_id": ts.id,
            "title": ts.title,
            "transcript": transcript,
            "metrics_summary": (fb.metrics_summary if fb else {}) or {},
            "feedback": feedback_block or {},
        },
        "historical": _historical_block(user_id, ts.channel_id, session, exclude_session_id=session_id),
    }
