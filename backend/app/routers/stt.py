"""Realtime speech-to-text WebSocket for the Chrome extension side panel.

The side panel streams 16kHz mono PCM here; we proxy it to ElevenLabs Scribe
realtime v2 and stream transcript frames back. See services/elevenlabs.py.
"""
from fastapi import APIRouter, WebSocket

from app.services import elevenlabs

router = APIRouter(tags=["stt"])


@router.websocket("/ws/stt")
async def stt_ws(websocket: WebSocket):
    await websocket.accept()
    await elevenlabs.proxy_realtime_stt(websocket)
