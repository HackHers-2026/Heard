"""Transcription + AI feedback endpoints.

Flow:
  - Extension streams practice audio/text -> /feedback/live -> Gemini pop-up tip
  - When the user stops -> /feedback/summarize -> summary + score into the DB,
    improvement score recomputed, and the row synced to TigerTable.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.security import get_current_user
from app.database import get_session
from app.models import Feedback, FeedbackKind, PracticeSession, Transcript, User
from app.schemas import (
    LiveFeedbackResponse,
    SummaryResponse,
    TranscribeRequest,
)
from app.services import backboard, elevenlabs, gemini, scoring, tigertable

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _owned_session(session_id: int, current: User, session: Session) -> PracticeSession:
    run = session.get(PracticeSession, session_id)
    if not run or run.user_id != current.id:
        raise HTTPException(404, "Session not found")
    return run


@router.post("/transcribe")
async def transcribe(
    session_id: int,
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Optional server-side transcription: extension uploads an audio chunk."""
    _owned_session(session_id, current, session)
    audio = await file.read()
    text = await elevenlabs.transcribe_audio(audio, file.content_type or "audio/webm")
    return {"session_id": session_id, "text": text}


@router.post("/live", response_model=LiveFeedbackResponse)
async def live(
    payload: TranscribeRequest,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Real-time coaching tip for a transcript chunk (rendered as a pop-up)."""
    run = _owned_session(payload.session_id, current, session)

    await backboard.append_memory(run.backboard_thread_id, "user", payload.text)
    result = await gemini.live_feedback(run.backboard_thread_id, run.domain.value, payload.text)
    await backboard.append_memory(run.backboard_thread_id, "coach", result["feedback"])

    fb = Feedback(
        session_id=run.id,
        kind=FeedbackKind.live,
        trigger_text=payload.text,
        content=result["feedback"],
    )
    session.add(fb)
    # Accumulate the raw transcript too.
    session.add(Transcript(session_id=run.id, text=payload.text, duration_seconds=payload.duration_seconds))
    session.commit()

    return LiveFeedbackResponse(
        session_id=run.id,
        trigger_text=payload.text,
        feedback=result["feedback"],
        tip_category=result.get("tip_category", "clarity"),
    )


@router.post("/summarize", response_model=SummaryResponse)
async def summarize(
    session_id: int,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """End of practice: build the summary + score, update leaderboard + TigerTable."""
    run = _owned_session(session_id, current, session)

    transcripts = session.exec(
        select(Transcript).where(Transcript.session_id == session_id)
    ).all()
    full_text = " ".join(t.text for t in transcripts) or "(no transcript captured)"

    result = await gemini.summarize(run.backboard_thread_id, run.domain.value, full_text)

    run.score = float(result["score"])
    session.add(run)
    session.add(
        Feedback(
            session_id=run.id,
            kind=FeedbackKind.summary,
            content=result["summary"],
            score=run.score,
        )
    )

    # Recompute the user's rolling improvement score from their session history.
    past_scores = [
        s.score
        for s in session.exec(
            select(PracticeSession)
            .where(PracticeSession.user_id == current.id)
            .order_by(PracticeSession.created_at)
        ).all()
        if s.score is not None
    ]
    current.improvement_score = scoring.compute_improvement_score(past_scores)
    session.add(current)
    session.commit()

    await tigertable.sync_practice(
        {
            "user_id": current.id,
            "display_name": current.display_name,
            "domain": run.domain.value,
            "score": run.score,
            "improvement_score": current.improvement_score,
            "session_id": run.id,
        }
    )

    return SummaryResponse(
        session_id=run.id,
        summary=result["summary"],
        score=run.score,
        strengths=result.get("strengths", []),
        improvements=result.get("improvements", []),
    )
