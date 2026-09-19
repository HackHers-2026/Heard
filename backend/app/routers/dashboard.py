from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from sqlalchemy import or_

from app.database import get_session
from app.dependencies import get_current_user
from app.models import ChatMessage, MentorConnection, Speech, User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _initials(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def _format_relative_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return ""

    now = datetime.utcnow()
    diff = now - dt
    if diff.days <= 0:
        return "Now"
    if diff.days == 1:
        return "Yesterday"
    if diff.days < 7:
        return dt.strftime("%a")
    return dt.strftime("%b %d")


@router.get("/bootstrap")
def bootstrap_dashboard(
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    user_row = session.get(User, user.id)
    display_name = getattr(user_row, "name", None) or getattr(user, "name", None) or "You"

    speeches = session.exec(
        select(Speech)
        .where(Speech.user_id == user.id)
        .order_by(Speech.started_at.desc())
    ).all()

    speech_payload: list[dict[str, Any]] = []
    for speech in speeches:
        latest = session.exec(
            select(ChatMessage)
            .where(ChatMessage.speech_id == speech.id)
            .order_by(ChatMessage.created_at.desc())
        ).first()
        title = (latest.summary if latest and latest.summary else None) or "Practice session"
        preview = latest.content if latest else ""
        speech_payload.append(
            {
                "id": speech.id,
                "title": title,
                "started_at": speech.started_at,
                "last_message": preview,
                "last_message_at": latest.created_at if latest else speech.started_at,
                "time_label": _format_relative_time(latest.created_at if latest else speech.started_at),
                "unread_count": 0,
            }
        )

    connections = session.exec(
        select(MentorConnection)
        .where(or_(MentorConnection.requester_id == user.id, MentorConnection.mentor_id == user.id))
        .order_by(MentorConnection.created_at.desc())
    ).all()

    contacts_by_id: dict[str, dict[str, Any]] = {}
    for connection in connections:
        contact_id = connection.mentor_id if connection.requester_id == user.id else connection.requester_id
        if contact_id in contacts_by_id:
            continue
        contact_row = session.get(User, contact_id)
        if not contact_row:
            continue

        latest = None
        speech_id = None
        if connection.speech_id:
            speech = session.get(Speech, connection.speech_id)
            if speech and speech.user_id == user.id:
                speech_id = speech.id
        if speech_id:
            latest = session.exec(
                select(ChatMessage)
                .where(ChatMessage.speech_id == speech_id)
                .order_by(ChatMessage.created_at.desc())
            ).first()

        contacts_by_id[contact_id] = {
            "id": contact_row.id,
            "name": contact_row.name,
            "initials": _initials(contact_row.name),
            "status": connection.status.capitalize(),
            "preview": latest.content if latest else "No conversation yet",
            "time_label": _format_relative_time(latest.created_at if latest else connection.created_at),
            "unread_count": 0,
            "speech_id": speech_id,
        }

    if not contacts_by_id:
        mentors = session.exec(
            select(User)
            .where(User.is_mentor == True, User.id != user.id)
            .order_by(User.created_at.desc())
        ).all()
        for mentor in mentors:
            contacts_by_id[mentor.id] = {
                "id": mentor.id,
                "name": mentor.name,
                "initials": _initials(mentor.name),
                "status": "Mentor",
                "preview": "Available to connect",
                "time_label": "",
                "unread_count": 0,
                "speech_id": None,
            }

    contacts = list(contacts_by_id.values())

    return {
        "user": {
            "id": user.id,
            "name": display_name,
            "avatar_initials": _initials(display_name),
            "online": True,
        },
        "speeches": speech_payload,
        "active_speech_id": speech_payload[0]["id"] if speech_payload else None,
        "contacts": contacts,
        "active_contact_id": contacts[0]["id"] if contacts else None,
    }
