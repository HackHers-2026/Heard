"""Channel + membership endpoints."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.services import channels as channels_svc

router = APIRouter(prefix="/api", tags=["channels"])


@router.get("/channels")
def list_channels(user=Depends(get_current_user), session: Session = Depends(get_session)):
    joined_ids = {c.id for c in channels_svc.my_channels(user.id, session)}
    return {
        "channels": [
            channels_svc.serialize_channel(c, joined=c.id in joined_ids)
            for c in channels_svc.list_channels(session)
        ]
    }


@router.get("/channels/{channel_id}")
def get_channel(channel_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    channel = channels_svc.get_channel(channel_id, session)
    joined = channels_svc.is_member(user.id, channel.id, session)
    return {"channel": channels_svc.serialize_channel(channel, joined=joined)}


@router.post("/channels/{channel_id}/join")
def join_channel(channel_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    channels_svc.join_channel(user.id, channel_id, session)
    channel = channels_svc.get_channel(channel_id, session)
    return {"channel": channels_svc.serialize_channel(channel, joined=True)}


@router.delete("/channels/{channel_id}/leave")
def leave_channel(channel_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    channels_svc.leave_channel(user.id, channel_id, session)
    channel = channels_svc.get_channel(channel_id, session)
    return {"channel": channels_svc.serialize_channel(channel, joined=False)}


@router.get("/me/channels")
def my_channels(user=Depends(get_current_user), session: Session = Depends(get_session)):
    return {
        "channels": [
            channels_svc.serialize_channel(c, joined=True)
            for c in channels_svc.my_channels(user.id, session)
        ]
    }
