"""Pre-training + generic thread/message endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import THREAD_PRE_TRAINING
from app.services import channels as channels_svc, threads as threads_svc

router = APIRouter(prefix="/api", tags=["threads"])


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None  # optional first user message


class MessageRequest(BaseModel):
    content: str


@router.get("/channels/{channel_id}/pre-training/threads")
def list_pretraining_threads(
    channel_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    channel = channels_svc.get_channel(channel_id, session)
    rows = threads_svc.list_threads(
        user.id, channel.id, THREAD_PRE_TRAINING, session, limit=limit, offset=offset
    )
    return {"threads": [threads_svc.serialize_thread(t) for t in rows]}


@router.post("/channels/{channel_id}/pre-training/threads")
async def create_pretraining_thread(
    channel_id: str,
    body: CreateThreadRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    channel = channels_svc.get_channel(channel_id, session)
    thread = threads_svc.create_thread(
        user.id, channel.id, THREAD_PRE_TRAINING, session,
        title=body.title or "New prep chat",
    )
    result = {"thread": threads_svc.serialize_thread(thread), "messages": []}
    if body.message and body.message.strip():
        turn = await threads_svc.post_user_message(thread, body.message, session)
        result["messages"] = [turn["message"], turn["reply"]]
    return result


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    thread = threads_svc.get_owned_thread(thread_id, user.id, session)
    messages = threads_svc.get_messages(thread_id, session)
    return {
        "thread": threads_svc.serialize_thread(thread),
        "messages": [threads_svc.serialize_message(m) for m in messages],
    }


@router.post("/threads/{thread_id}/messages")
async def post_message(
    thread_id: str,
    body: MessageRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    thread = threads_svc.get_owned_thread(thread_id, user.id, session)
    return await threads_svc.post_user_message(thread, body.content, session)
