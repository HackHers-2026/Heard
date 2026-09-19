"""Realtime speech-to-text WebSocket for the Chrome extension side panel.

The side panel streams 16kHz mono PCM here; we proxy it to ElevenLabs Scribe
realtime v2 and stream transcript frames back (see services/elevenlabs.py).

While streaming, committed transcript text is accumulated and written to the DB
as one `RealtimeSegment` per minute. Every segment shares the same `speech_id`
(the session ID) created when the socket opens. See services/segmenter.py.
"""
import asyncio

from fastapi import APIRouter, WebSocket
from sqlmodel import Session

from app.database import engine
from app.dependencies import authenticate_token
from app.services import elevenlabs
from app.services.segmenter import SpeechSegmenter

router = APIRouter(tags=["stt"])


def _resolve_user_id(websocket: WebSocket) -> str | None:
    """Authenticate the socket from a `?token=<jwt>` query param.

    Browser WebSocket clients can't set an Authorization header, so the side
    panel appends the Supabase JWT as a query param. Returns the real user id
    when the token is valid, or None so the segmenter falls back to the demo
    user (keeps the pipeline working before auth is wired up)."""
    token = websocket.query_params.get("token")
    if not token:
        return None
    with Session(engine) as session:
        user = authenticate_token(token, session)
        return user.id if user else None


async def _flush_every_minute(segmenter: SpeechSegmenter) -> None:
    """Write a segment once per minute for as long as the socket is open."""
    try:
        while True:
            await asyncio.sleep(segmenter.segment_seconds)
            await segmenter.force_flush()
    except asyncio.CancelledError:
        pass


@router.websocket("/ws/stt")
async def stt_ws(websocket: WebSocket):
    await websocket.accept()

    # Attribute the session to the signed-in user when a valid token is present.
    user_id = _resolve_user_id(websocket)

    # One recording == one Speech (session). All segments share this id.
    segmenter = SpeechSegmenter(user_id=user_id)
    await websocket.send_json(
        {
            "type": "session",
            "speech_id": segmenter.speech_id,
            "authenticated": user_id is not None,
        }
    )

    async def on_transcript(text: str, is_final: bool) -> None:
        # Only finalized (committed) text becomes part of a stored segment.
        if is_final:
            await segmenter.add_committed(text)

    flush_task = asyncio.create_task(_flush_every_minute(segmenter))
    try:
        await elevenlabs.proxy_realtime_stt(websocket, on_transcript=on_transcript)
    finally:
        flush_task.cancel()
        await segmenter.flush_remaining()  # persist the final partial minute
        segmenter.end()                    # mark the session finished
