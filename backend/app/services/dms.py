"""Internal 1:1 direct messages.

A deterministic ``pair_key`` (sorted user ids) makes duplicate 1:1 conversations
impossible. Only conversation members may read or write, and ``sender_id`` is
always the authenticated user — never trusted from the client.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.errors import APIError
from app.models import DMConversation, DMMember, DMMessage, Profile


def _pair_key(a: str, b: str) -> str:
    return "|".join(sorted([a, b]))


def _members(conversation_id: str, session: Session) -> list[str]:
    rows = session.exec(
        select(DMMember.user_id).where(DMMember.conversation_id == conversation_id)
    ).all()
    return list(rows)


def _require_member(conversation_id: str, user_id: str, session: Session) -> DMConversation:
    convo = session.get(DMConversation, conversation_id)
    if not convo:
        raise APIError(404, "DM_NOT_FOUND", "Conversation was not found.")
    if user_id not in _members(conversation_id, session):
        raise APIError(403, "DM_FORBIDDEN", "You are not a member of this conversation.")
    return convo


def get_or_create_with(user_id: str, other_id: str, session: Session) -> DMConversation:
    if user_id == other_id:
        raise APIError(422, "DM_SELF", "You cannot start a conversation with yourself.")
    if not session.get(Profile, other_id):
        raise APIError(404, "USER_NOT_FOUND", "That user does not exist.")

    key = _pair_key(user_id, other_id)
    convo = session.exec(
        select(DMConversation).where(DMConversation.pair_key == key)
    ).first()
    if convo:
        return convo

    convo = DMConversation(pair_key=key)
    session.add(convo)
    session.commit()
    session.refresh(convo)
    session.add(DMMember(conversation_id=convo.id, user_id=user_id))
    session.add(DMMember(conversation_id=convo.id, user_id=other_id))
    session.commit()
    return convo


def unread_count(conversation_id: str, user_id: str, session: Session) -> int:
    rows = session.exec(
        select(DMMessage).where(
            DMMessage.conversation_id == conversation_id,
            DMMessage.sender_id != user_id,
            DMMessage.read_at == None,  # noqa: E711
        )
    ).all()
    return len(rows)


def _last_message(conversation_id: str, session: Session) -> Optional[DMMessage]:
    return session.exec(
        select(DMMessage)
        .where(DMMessage.conversation_id == conversation_id)
        .order_by(DMMessage.created_at.desc())
    ).first()


def list_conversations(user_id: str, session: Session) -> list[dict]:
    convo_ids = session.exec(
        select(DMMember.conversation_id).where(DMMember.user_id == user_id)
    ).all()
    result = []
    for cid in convo_ids:
        convo = session.get(DMConversation, cid)
        if not convo:
            continue
        other_ids = [m for m in _members(cid, session) if m != user_id]
        other = session.get(Profile, other_ids[0]) if other_ids else None
        last = _last_message(cid, session)
        result.append({
            "id": convo.id,
            "updated_at": convo.updated_at,
            "other_user": {
                "user_id": other.id,
                "display_name": other.display_name,
                "username": other.username,
                "avatar_url": other.avatar_url,
            } if other else None,
            "last_message": serialize_message(last) if last else None,
            "unread_count": unread_count(cid, user_id, session),
        })
    result.sort(key=lambda c: c["updated_at"], reverse=True)
    return result


def get_messages(
    conversation_id: str, user_id: str, session: Session,
    *, limit: int = 50, offset: int = 0,
) -> list[DMMessage]:
    _require_member(conversation_id, user_id, session)
    rows = session.exec(
        select(DMMessage)
        .where(DMMessage.conversation_id == conversation_id)
        .order_by(DMMessage.created_at)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows)


def send_message(conversation_id: str, user_id: str, content: str, session: Session) -> DMMessage:
    convo = _require_member(conversation_id, user_id, session)
    if not content or not content.strip():
        raise APIError(422, "EMPTY_MESSAGE", "Message content cannot be empty.")
    msg = DMMessage(conversation_id=conversation_id, sender_id=user_id, content=content.strip())
    session.add(msg)
    convo.updated_at = datetime.utcnow().isoformat()
    session.add(convo)
    session.commit()
    session.refresh(msg)
    return msg


def mark_read(conversation_id: str, user_id: str, session: Session) -> int:
    _require_member(conversation_id, user_id, session)
    now = datetime.utcnow().isoformat()
    rows = session.exec(
        select(DMMessage).where(
            DMMessage.conversation_id == conversation_id,
            DMMessage.sender_id != user_id,
            DMMessage.read_at == None,  # noqa: E711
        )
    ).all()
    for m in rows:
        m.read_at = now
        session.add(m)
    session.commit()
    return len(rows)


def serialize_message(m: DMMessage) -> dict:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "content": m.content,
        "created_at": m.created_at,
        "read_at": m.read_at,
    }
