"""Direct messages: struggling users can reach out to mentors on the leaderboard."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, or_, select

from app.core.security import get_current_user
from app.database import get_session
from app.models import Message, User
from app.schemas import MessageCreate, MessagePublic

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessagePublic, status_code=201)
def send_message(
    payload: MessageCreate,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    recipient = session.get(User, payload.recipient_id)
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    msg = Message(sender_id=current.id, recipient_id=payload.recipient_id, body=payload.body)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


@router.get("/thread/{other_user_id}", response_model=list[MessagePublic])
def thread(
    other_user_id: int,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Full DM thread between the current user and another user."""
    msgs = session.exec(
        select(Message)
        .where(
            or_(
                (Message.sender_id == current.id) & (Message.recipient_id == other_user_id),
                (Message.sender_id == other_user_id) & (Message.recipient_id == current.id),
            )
        )
        .order_by(Message.created_at)
    ).all()
    return msgs


@router.get("/inbox", response_model=list[MessagePublic])
def inbox(
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Message)
        .where(Message.recipient_id == current.id)
        .order_by(Message.created_at.desc())
    ).all()
