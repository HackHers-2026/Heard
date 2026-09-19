"""Internal 1:1 direct-message endpoints."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.services import dms as dms_svc

router = APIRouter(prefix="/api/dms", tags=["dms"])


class DMMessageRequest(BaseModel):
    content: str


@router.post("/with/{user_id}")
def open_conversation(
    user_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    convo = dms_svc.get_or_create_with(user.id, user_id, session)
    return {"conversation_id": convo.id, "created_at": convo.created_at}


@router.get("")
def list_conversations(user=Depends(get_current_user), session: Session = Depends(get_session)):
    return {"conversations": dms_svc.list_conversations(user.id, session)}


@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    msgs = dms_svc.get_messages(conversation_id, user.id, session, limit=limit, offset=offset)
    return {"messages": [dms_svc.serialize_message(m) for m in msgs]}


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    body: DMMessageRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    msg = dms_svc.send_message(conversation_id, user.id, body.content, session)
    return {"message": dms_svc.serialize_message(msg)}


@router.post("/{conversation_id}/read")
def mark_read(
    conversation_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    count = dms_svc.mark_read(conversation_id, user.id, session)
    return {"marked_read": count}
