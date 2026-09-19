"""Training-session endpoints: create, ingest segments, complete, history."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.services import (
    sessions as sessions_svc, threads as threads_svc,
    progress as progress_svc, leaderboard as leaderboard_svc,
)

router = APIRouter(prefix="/api", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


class SegmentRequest(BaseModel):
    segment_index: int
    transcript: str = ""
    start_seconds: float = 0
    end_seconds: float = 0
    duration_seconds: Optional[float] = None
    audio_metrics: Optional[dict] = None


@router.post("/channels/{channel_id}/sessions")
def create_session(
    channel_id: str,
    body: CreateSessionRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ts, thread = sessions_svc.create_session(user.id, channel_id, body.title or "", session)
    return {
        "session": sessions_svc.serialize_session(ts),
        "thread": threads_svc.serialize_thread(thread),
        "session_id": ts.id,
        "thread_id": thread.id,
    }


@router.post("/sessions/{session_id}/segments")
def add_segment(
    session_id: str,
    body: SegmentRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    seg = sessions_svc.ingest_segment(session_id, user.id, body.model_dump(), session)
    return {"segment": sessions_svc.serialize_segment(seg)}


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    fb = await sessions_svc.complete_session(session_id, user.id, session)
    ts = sessions_svc.get_owned_session(session_id, user.id, session)
    return {
        "session": sessions_svc.serialize_session(ts),
        "feedback": sessions_svc.serialize_feedback(fb),
        "recommended_peers": leaderboard_svc.recommended_peers(ts.channel_id, user.id, session),
    }


@router.get("/me/sessions")
def my_sessions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rows = sessions_svc.list_sessions(user.id, session, limit=limit, offset=offset)
    return {"sessions": [sessions_svc.serialize_session(s) for s in rows]}


@router.get("/channels/{channel_id}/sessions")
def channel_sessions(
    channel_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rows = sessions_svc.list_sessions(
        user.id, session, channel_id=channel_id, limit=limit, offset=offset
    )
    return {"sessions": [sessions_svc.serialize_session(s) for s in rows]}


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ts = sessions_svc.get_owned_session(session_id, user.id, session)
    thread = sessions_svc._post_thread_for_session(ts.id, session)
    fb = sessions_svc.get_feedback(ts.id, session)
    return {
        "session": sessions_svc.serialize_session(ts),
        "thread": threads_svc.serialize_thread(thread) if thread else None,
        "feedback": sessions_svc.serialize_feedback(fb) if fb else None,
        "progress": progress_svc.channel_progress(user.id, ts.channel_id, session),
        "recommended_peers": leaderboard_svc.recommended_peers(ts.channel_id, user.id, session),
    }


@router.get("/sessions/{session_id}/segments")
def get_session_segments(
    session_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    sessions_svc.get_owned_session(session_id, user.id, session)
    segs = sessions_svc.get_segments(session_id, session)
    return {"segments": [sessions_svc.serialize_segment(s) for s in segs]}


@router.get("/sessions/{session_id}/feedback")
def get_session_feedback(
    session_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    sessions_svc.get_owned_session(session_id, user.id, session)
    fb = sessions_svc.get_feedback(session_id, session)
    from app.errors import APIError
    if not fb:
        raise APIError(404, "FEEDBACK_NOT_FOUND", "Feedback is not available yet.")
    return {"feedback": sessions_svc.serialize_feedback(fb)}
