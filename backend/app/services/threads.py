"""Thread + message service.

Supabase is the source of truth for every chat message. A thread is either
PRE_TRAINING (free-form prep conversation) or POST_TRAINING (grounded in a
completed session). Posting a message: save the user turn, load prior context,
ask the AI coach, save + return the assistant turn.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.errors import APIError
from app.models import (
    ChatThread, ThreadMessage, THREAD_PRE_TRAINING, THREAD_POST_TRAINING,
)
from app.services import ai_coach, context_builder


# ─────────────────────────────────────────────────────────────────────────────
# Serialization
# ─────────────────────────────────────────────────────────────────────────────

def serialize_thread(thread: ChatThread) -> dict:
    return {
        "id": thread.id,
        "user_id": thread.user_id,
        "channel_id": thread.channel_id,
        "thread_type": thread.thread_type,
        "session_id": thread.session_id,
        "title": thread.title,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def serialize_message(m: ThreadMessage) -> dict:
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "sender_type": m.sender_type,
        "content": m.content,
        "metadata": m.message_metadata or {},
        "created_at": m.created_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

def get_owned_thread(thread_id: str, user_id: str, session: Session) -> ChatThread:
    thread = session.get(ChatThread, thread_id)
    if not thread:
        raise APIError(404, "THREAD_NOT_FOUND", "Thread was not found.")
    if thread.user_id != user_id:
        raise APIError(403, "THREAD_FORBIDDEN", "You do not have access to this thread.")
    return thread


def create_thread(
    user_id: str, channel_id: str, thread_type: str, session: Session,
    *, title: str = "", session_id: Optional[str] = None,
) -> ChatThread:
    thread = ChatThread(
        user_id=user_id,
        channel_id=channel_id,
        thread_type=thread_type,
        title=title,
        session_id=session_id,
    )
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return thread


def list_threads(
    user_id: str, channel_id: str, thread_type: str, session: Session,
    *, limit: int = 50, offset: int = 0,
) -> list[ChatThread]:
    rows = session.exec(
        select(ChatThread)
        .where(
            ChatThread.user_id == user_id,
            ChatThread.channel_id == channel_id,
            ChatThread.thread_type == thread_type,
        )
        .order_by(ChatThread.updated_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows)


def get_messages(thread_id: str, session: Session, *, limit: int = 200, offset: int = 0) -> list[ThreadMessage]:
    rows = session.exec(
        select(ThreadMessage)
        .where(ThreadMessage.thread_id == thread_id)
        .order_by(ThreadMessage.created_at)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows)


def add_message(
    thread_id: str, sender_type: str, content: str, session: Session,
    *, metadata: Optional[dict] = None, touch: bool = True,
) -> ThreadMessage:
    msg = ThreadMessage(
        thread_id=thread_id,
        sender_type=sender_type,
        content=content,
        message_metadata=metadata or {},
    )
    session.add(msg)
    if touch:
        thread = session.get(ChatThread, thread_id)
        if thread:
            thread.updated_at = datetime.utcnow().isoformat()
            session.add(thread)
    session.commit()
    session.refresh(msg)
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# AI conversation turn — grounded in Supabase context, stateful via Backboard
# ─────────────────────────────────────────────────────────────────────────────

async def post_user_message(thread: ChatThread, content: str, session: Session) -> dict:
    """Save the user turn, generate + save the assistant turn, return both.

    Both pre- and post-training turns receive explicit Supabase-sourced context
    (never a blank chatbot). The Backboard thread id is persisted for continuity.
    """
    if not content or not content.strip():
        raise APIError(422, "EMPTY_MESSAGE", "Message content cannot be empty.")

    user_msg = add_message(thread.id, "user", content.strip(), session)

    if thread.thread_type == THREAD_POST_TRAINING and thread.session_id:
        context = context_builder.build_posttraining_chat_context(
            thread.user_id, thread.session_id, session
        )
        reply, backboard_tid = await ai_coach.posttraining_reply(
            thread.user_id, thread, context, content.strip()
        )
    else:
        context = context_builder.build_pretraining_context(
            thread.user_id, thread.channel_id, session
        )
        reply, backboard_tid = await ai_coach.pretraining_reply(
            thread.user_id, thread, context, content.strip()
        )

    # Persist the Backboard thread id the first time it is minted.
    if backboard_tid and backboard_tid != thread.backboard_thread_id:
        thread.backboard_thread_id = backboard_tid
        session.add(thread)
        session.commit()

    assistant_msg = add_message(thread.id, "assistant", reply, session)
    return {
        "message": serialize_message(user_msg),
        "reply": serialize_message(assistant_msg),
    }
