"""Practice sessions: create a run, list a user's runs, fetch its chat thread."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.security import get_current_user
from app.database import get_session
from app.models import Feedback, PracticeSession, Transcript, User
from app.schemas import FeedbackPublic, SessionCreate, SessionPublic
from app.services import backboard

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionPublic, status_code=201)
async def create_session(
    payload: SessionCreate,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    thread_id = await backboard.create_thread(current.id, payload.domain.value)
    run = PracticeSession(
        user_id=current.id,
        domain=payload.domain,
        title=payload.title,
        slides_url=payload.slides_url,
        backboard_thread_id=thread_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.get("", response_model=list[SessionPublic])
def list_sessions(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(PracticeSession).where(PracticeSession.user_id == current.id)
    ).all()


@router.get("/{session_id}/feedback", response_model=list[FeedbackPublic])
def session_feedback(
    session_id: int,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The 'text chat with the AI': all feedback items for a run, in order."""
    run = session.get(PracticeSession, session_id)
    if not run or run.user_id != current.id:
        raise HTTPException(404, "Session not found")
    return session.exec(
        select(Feedback).where(Feedback.session_id == session_id).order_by(Feedback.created_at)
    ).all()


@router.get("/{session_id}/transcript")
def session_transcript(
    session_id: int,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.get(PracticeSession, session_id)
    if not run or run.user_id != current.id:
        raise HTTPException(404, "Session not found")
    return session.exec(
        select(Transcript).where(Transcript.session_id == session_id)
    ).all()
