"""Progress, leaderboard, and recommended-peers endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.services import (
    progress as progress_svc, leaderboard as leaderboard_svc,
    performance_profiles as perf_svc, channels as channels_svc,
)

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/me/channels/{channel_id}/progress")
def channel_progress(
    channel_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    result = progress_svc.channel_progress(user.id, channel_id, session)
    channel = channels_svc.get_channel(channel_id, session)
    profile = perf_svc.get_profile(user.id, channel.id, session)
    result["performance_profile"] = perf_svc.serialize(profile) if profile else None
    return result


@router.get("/channels/{channel_id}/leaderboard")
def channel_leaderboard(
    channel_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return leaderboard_svc.channel_leaderboard(
        channel_id, session, viewer_id=user.id, limit=limit, offset=offset
    )


@router.get("/channels/{channel_id}/recommended-peers")
def recommended_peers(
    channel_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return {"peers": leaderboard_svc.recommended_peers(channel_id, user.id, session)}
