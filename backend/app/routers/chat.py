from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.dependencies import get_current_user
from app.models import ChatMessage, Speech
from app.services.gemini import chat as gemini_chat, make_session_hash

router = APIRouter(prefix="/api/speech", tags=["chat"])

VALID_PHASES = {"preptalk", "activetalk", "talksummary"}


class ChatRequest(BaseModel):
    message: str
    phase: str = "preptalk"


@router.post("/{speech_id}/chat")
def post_chat(
    speech_id: str,
    body: ChatRequest,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    if body.phase not in VALID_PHASES:
        raise HTTPException(status_code=422, detail=f"phase must be one of {VALID_PHASES}")

    speech = session.get(Speech, speech_id)
    if not speech or speech.user_id != user.id:
        raise HTTPException(status_code=404, detail="Speech not found")

    return gemini_chat(speech_id, body.message, body.phase, session)


@router.get("/{speech_id}/chat")
def get_chat(
    speech_id: str,
    phase: Optional[str] = None,
    limit: Optional[int] = None,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    speech = session.get(Speech, speech_id)
    if not speech or speech.user_id != user.id:
        raise HTTPException(status_code=404, detail="Speech not found")

    session_hash = make_session_hash(speech_id)
    q = select(ChatMessage).where(ChatMessage.session_hash == session_hash)
    if phase:
        q = q.where(ChatMessage.phase == phase)
    q = q.order_by(ChatMessage.created_at)

    messages = session.exec(q).all()

    # limit=3 → last 3 exchanges = last 6 rows (user + model per exchange)
    if limit is not None:
        messages = messages[-(limit * 2):]

    return {
        "messages": [
            {
                "role": m.role,
                "phase": m.phase,
                "content": m.content,
                "summary": m.summary,
                "created_at": m.created_at,
            }
            for m in messages
        ]
    }
