"""Training-session lifecycle: create → ingest rich segments → complete + analyze.

Completion assembles a SESSION EVIDENCE PACKET (deterministic metrics) plus
CHANNEL-SPECIFIC HISTORY, sends both to Backboard/Gemini for longitudinal
analysis, persists the structured result, and refreshes the user's per-channel
performance memory. Runs synchronously for the MVP but is structured as a
service so it can move to a background worker.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.errors import APIError
from app.models import (
    TrainingSession, TranscriptSegment, SessionFeedback, ChatThread,
    THREAD_POST_TRAINING, SESSION_ACTIVE, SESSION_PROCESSING,
    SESSION_COMPLETED, SESSION_FAILED,
)
from app.services import (
    analysis, ai_coach, channels as channels_svc, threads as threads_svc,
    context_builder, performance_profiles,
)


# ─────────────────────────────────────────────────────────────────────────────
# Ownership + serialization
# ─────────────────────────────────────────────────────────────────────────────

def get_owned_session(session_id: str, user_id: str, session: Session) -> TrainingSession:
    ts = session.get(TrainingSession, session_id)
    if not ts:
        raise APIError(404, "SESSION_NOT_FOUND", "Training session was not found.")
    if ts.user_id != user_id:
        raise APIError(403, "SESSION_FORBIDDEN", "You do not have access to this session.")
    return ts


def serialize_session(ts: TrainingSession) -> dict:
    return {
        "id": ts.id,
        "user_id": ts.user_id,
        "channel_id": ts.channel_id,
        "title": ts.title,
        "status": ts.status,
        "started_at": ts.started_at,
        "ended_at": ts.ended_at,
        "duration_seconds": ts.duration_seconds,
        "total_words": ts.total_words,
        "created_at": ts.created_at,
    }


def serialize_segment(s: TranscriptSegment) -> dict:
    return {
        "id": s.id,
        "session_id": s.session_id,
        "segment_index": s.segment_index,
        "transcript": s.transcript,
        "start_seconds": s.start_seconds,
        "end_seconds": s.end_seconds,
        "duration_seconds": s.duration_seconds,
        "word_count": s.word_count,
        "audio_metrics": s.audio_metrics or {},
        "created_at": s.created_at,
    }


def serialize_feedback(fb: SessionFeedback) -> dict:
    return {
        "id": fb.id,
        "session_id": fb.session_id,
        "scores": {
            "clarity": fb.clarity_score,
            "conciseness": fb.conciseness_score,
            "pace": fb.pace_score,
            "volume": fb.volume_score,
            "confidence": fb.confidence_score,
            "structure": fb.structure_score,
        },
        "overall_score": fb.overall_score,
        "unavailable_dimensions": fb.unavailable_dimensions or [],
        "filler_count": fb.filler_count,
        "filler_rate": fb.filler_rate,
        "average_wpm": fb.average_wpm,
        "volume_consistency": fb.volume_consistency,
        "summary": fb.summary,
        "strengths": fb.strengths or [],
        "improvements": fb.improvements or [],
        "strongest_moments": fb.strongest_moments or [],
        "priority_moments": fb.priority_moments or [],
        "persistent_patterns": fb.persistent_patterns or [],
        "new_patterns": fb.new_patterns or [],
        "stable_strengths": fb.stable_strengths or [],
        "next_session_goals": fb.next_session_goals or [],
        "metrics_interpretation": fb.metrics_interpretation or {},
        "vocal_variety": fb.vocal_variety or {},
        "metrics_summary": fb.metrics_summary or {},
        "longitudinal_analysis": fb.longitudinal_analysis or {},
        "created_at": fb.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

def create_session(user_id: str, channel_id: str, title: str, session: Session) -> tuple[TrainingSession, ChatThread]:
    channel = channels_svc.get_channel(channel_id, session)
    title = title or f"Practice - {datetime.utcnow().strftime('%b %d')}"

    ts = TrainingSession(user_id=user_id, channel_id=channel.id, title=title, status=SESSION_ACTIVE)
    session.add(ts)
    session.commit()
    session.refresh(ts)

    thread = threads_svc.create_thread(
        user_id, channel.id, THREAD_POST_TRAINING, session,
        title=title, session_id=ts.id,
    )
    threads_svc.add_message(
        thread.id, "system", "Training session started.", session,
        metadata={"session_id": ts.id}, touch=False,
    )
    return ts, thread


def _post_thread_for_session(session_id: str, session: Session) -> Optional[ChatThread]:
    return session.exec(
        select(ChatThread).where(
            ChatThread.session_id == session_id,
            ChatThread.thread_type == THREAD_POST_TRAINING,
        )
    ).first()


# ─────────────────────────────────────────────────────────────────────────────
# Ingest a ~60-second transcript + audio-metrics segment
# ─────────────────────────────────────────────────────────────────────────────

def ingest_segment(session_id: str, user_id: str, payload: dict, session: Session) -> TranscriptSegment:
    ts = get_owned_session(session_id, user_id, session)
    if ts.status in (SESSION_COMPLETED, SESSION_FAILED):
        raise APIError(409, "SESSION_CLOSED", "Cannot add segments to a closed session.")

    segment_index = payload["segment_index"]
    transcript = payload.get("transcript", "") or ""
    start = float(payload.get("start_seconds", 0) or 0)
    end = float(payload.get("end_seconds", 0) or 0)
    duration = payload.get("duration_seconds")
    if duration is None:
        duration = max(0.0, end - start)
    audio_metrics = payload.get("audio_metrics") or {}

    existing = session.exec(
        select(TranscriptSegment).where(
            TranscriptSegment.session_id == ts.id,
            TranscriptSegment.segment_index == segment_index,
        )
    ).first()
    if existing:
        raise APIError(409, "DUPLICATE_SEGMENT", f"Segment {segment_index} already exists.")

    words = analysis.word_count(transcript)
    # WPM from speaking_duration when supplied, else fall back to segment duration.
    speaking = audio_metrics.get("speaking_duration_seconds")
    seg_wpm = analysis.wpm(words, speaking if speaking else duration)

    seg = TranscriptSegment(
        session_id=ts.id,
        segment_index=segment_index,
        transcript=transcript,
        start_seconds=start,
        end_seconds=end,
        duration_seconds=float(duration),
        word_count=words,
        audio_metrics=audio_metrics,
    )
    session.add(seg)

    ts.total_words = (ts.total_words or 0) + words
    ts.duration_seconds = (ts.duration_seconds or 0.0) + float(duration)
    session.add(ts)
    session.commit()
    session.refresh(seg)

    thread = _post_thread_for_session(ts.id, session)
    if thread:
        lang = analysis.language_stats(transcript)
        threads_svc.add_message(
            thread.id, "transcript", transcript, session,
            metadata={
                "segment_index": segment_index,
                "start_seconds": start,
                "end_seconds": end,
                "word_count": words,
                "wpm": seg_wpm,
                "filler_count": lang["filler_count"],
                "hedge_count": lang["hedge_count"],
                "audio_metrics": audio_metrics,
            },
            touch=False,
        )
    return seg


def get_segments(session_id: str, session: Session) -> list[TranscriptSegment]:
    return list(session.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.segment_index)
    ).all())


def get_feedback(session_id: str, session: Session) -> Optional[SessionFeedback]:
    return session.exec(
        select(SessionFeedback).where(SessionFeedback.session_id == session_id)
    ).first()


# ─────────────────────────────────────────────────────────────────────────────
# Complete + analyze (longitudinal)
# ─────────────────────────────────────────────────────────────────────────────

async def complete_session(session_id: str, user_id: str, session: Session) -> SessionFeedback:
    ts = get_owned_session(session_id, user_id, session)
    if ts.status == SESSION_COMPLETED:
        raise APIError(409, "SESSION_ALREADY_COMPLETED", "Session is already completed.")

    ts.status = SESSION_PROCESSING
    session.add(ts)
    session.commit()

    context = context_builder.build_session_analysis_context(user_id, ts.id, session)
    evidence = context["current_session"]

    # Edge case: no transcript → complete with an explicit, honest record (no AI).
    if evidence["pace"]["total_word_count"] == 0:
        fb = _persist_feedback(ts, evidence, None, context, session)
        _finalize(ts, evidence, session)
        _post_feedback_message(ts, fb, session)
        performance_profiles.update_after_session(user_id, ts.channel_id, session)
        return fb

    try:
        ai = await ai_coach.analyze_session(user_id, context)
    except ai_coach.AIAnalysisError:
        ts.status = SESSION_FAILED
        session.add(ts)
        session.commit()
        raise APIError(502, "AI_ANALYSIS_FAILED", "AI analysis could not be completed. Please retry.")

    fb = _persist_feedback(ts, evidence, ai, context, session)
    _finalize(ts, evidence, session)
    _post_feedback_message(ts, fb, session)
    performance_profiles.update_after_session(user_id, ts.channel_id, session)
    return fb


def _finalize(ts: TrainingSession, evidence: dict, session: Session) -> None:
    ts.status = SESSION_COMPLETED
    ts.ended_at = datetime.utcnow().isoformat()
    ts.total_words = evidence["pace"]["total_word_count"]
    if evidence["timing"]["total_duration_seconds"]:
        ts.duration_seconds = evidence["timing"]["total_duration_seconds"]
    session.add(ts)
    session.commit()


def _persist_feedback(
    ts: TrainingSession, evidence: dict,
    ai: Optional[ai_coach.SessionAnalysis], context: dict, session: Session,
) -> SessionFeedback:
    existing = get_feedback(ts.id, session)
    if existing:
        return existing

    lang = evidence.get("language", {})
    det = evidence.get("deterministic_scores", {})
    has_audio = evidence.get("has_audio_metrics", False)

    # Deterministic (objective) dimensions.
    pace = analysis.clamp_score(det.get("pace"))
    confidence = analysis.clamp_score(det.get("confidence"))
    conciseness = analysis.clamp_score(det.get("conciseness"))
    volume = analysis.clamp_score(det.get("volume")) if has_audio else None
    clarity = structure = None

    strengths: list = []
    improvements: list = []
    summary = ""
    strongest = priority = persistent = new_patterns = stable = goals = []
    metrics_interpretation: dict = {}
    longitudinal: dict = {}

    if ai is not None:
        s = ai.scores
        clarity = analysis.clamp_score(s.clarity)
        structure = analysis.clamp_score(s.structure)
        if s.conciseness is not None:
            conciseness = analysis.clamp_score(s.conciseness)
        if s.confidence is not None:
            confidence = analysis.clamp_score(s.confidence)
        # Only trust AI volume when audio metrics actually exist.
        if has_audio and s.volume is not None:
            volume = analysis.clamp_score(s.volume)
        summary = ai.current_session_summary
        strongest = [m.model_dump() for m in ai.strongest_moments]
        priority = [m.model_dump() for m in ai.priority_moments]
        persistent = [p.model_dump() for p in ai.persistent_patterns]
        new_patterns = [p.model_dump() for p in ai.new_patterns]
        stable = list(ai.stable_strengths)
        goals = [g.model_dump() for g in ai.top_3_next_session_goals]
        metrics_interpretation = ai.metrics_interpretation.model_dump()
        longitudinal = {
            "improvements_since_previous": [c.model_dump() for c in ai.improvements_since_previous],
            "regressions_since_previous": [c.model_dump() for c in ai.regressions_since_previous],
            "historical_summary": ai.historical_summary.model_dump(),
        }
        strengths = stable[:5]
        improvements = [g.get("goal") for g in goals if g.get("goal")] or \
                       [m.get("reason") for m in priority if m.get("reason")]
    else:
        summary = "No speech was captured for this session."

    unavailable = ["volume"] if volume is None else []

    overall = analysis.composite_score({
        "clarity": clarity, "conciseness": conciseness, "pace": pace,
        "volume": volume, "confidence": confidence, "structure": structure,
    })

    # Compact metrics summary (raw transcript/segments live in their own tables).
    metrics_summary = {
        "timing": evidence.get("timing"),
        "pace": evidence.get("pace"),
        "pauses": evidence.get("pauses"),
        "volume": evidence.get("volume"),
        "pitch": evidence.get("pitch"),
        "language": lang,
        "has_audio_metrics": has_audio,
        "deterministic_scores": det,
    }

    fb = SessionFeedback(
        session_id=ts.id,
        clarity_score=clarity,
        conciseness_score=conciseness,
        pace_score=pace,
        volume_score=volume,
        confidence_score=confidence,
        structure_score=structure,
        overall_score=overall,
        unavailable_dimensions=unavailable,
        filler_count=lang.get("filler_count", 0),
        filler_rate=lang.get("filler_rate", 0.0),
        average_wpm=evidence.get("pace", {}).get("average_wpm") or 0.0,
        volume_consistency=evidence.get("volume", {}).get("consistency"),
        strengths=strengths,
        improvements=improvements[:8],
        summary=summary,
        detailed_feedback={"metrics_summary": metrics_summary},
        metrics_summary=metrics_summary,
        longitudinal_analysis=longitudinal,
        strongest_moments=strongest,
        priority_moments=priority,
        persistent_patterns=persistent,
        new_patterns=new_patterns,
        stable_strengths=stable,
        next_session_goals=goals,
        metrics_interpretation=metrics_interpretation,
        vocal_variety=evidence.get("vocal_variety", {}),
    )
    session.add(fb)
    session.commit()
    session.refresh(fb)
    return fb


def _post_feedback_message(ts: TrainingSession, fb: SessionFeedback, session: Session) -> None:
    thread = _post_thread_for_session(ts.id, session)
    if not thread:
        return
    parts = [f"Session analysis complete. Overall score: {fb.overall_score}."]
    if fb.summary:
        parts.append(fb.summary)
    if fb.next_session_goals:
        goals = "; ".join(g.get("goal", "") for g in fb.next_session_goals[:3] if g.get("goal"))
        if goals:
            parts.append("Next-session goals: " + goals + ".")
    threads_svc.add_message(
        thread.id, "assistant", " ".join(parts), session,
        metadata={
            "session_id": ts.id,
            "scores": {
                "clarity": fb.clarity_score, "conciseness": fb.conciseness_score,
                "pace": fb.pace_score, "volume": fb.volume_score,
                "confidence": fb.confidence_score, "structure": fb.structure_score,
                "overall": fb.overall_score,
            },
            "priority_moments": fb.priority_moments or [],
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Listing
# ─────────────────────────────────────────────────────────────────────────────

def list_sessions(
    user_id: str, session: Session, *, channel_id: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[TrainingSession]:
    q = select(TrainingSession).where(TrainingSession.user_id == user_id)
    if channel_id:
        channel = channels_svc.get_channel(channel_id, session)
        q = q.where(TrainingSession.channel_id == channel.id)
    q = q.order_by(TrainingSession.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(q).all())
