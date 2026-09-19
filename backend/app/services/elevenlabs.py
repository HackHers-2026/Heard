"""ElevenLabs speech-to-text integration.

The Chrome extension captures microphone audio while the user practices over
Google Slides. Audio chunks are POSTed here and transcribed with ElevenLabs
Scribe. If no API key is configured we return a stub so the app still runs.

Docs: https://elevenlabs.io/docs/capabilities/speech-to-text
"""
from __future__ import annotations

import httpx

from app.config import settings

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


async def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    """Transcribe a chunk of audio into text.

    TODO(hackathon): stream partial results over a WebSocket for lower latency
    live feedback instead of chunked POSTs.
    """
    if not settings.elevenlabs_api_key:
        return "[stub transcript — set ELEVENLABS_API_KEY to enable transcription]"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _STT_URL,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            data={"model_id": settings.elevenlabs_stt_model},
            files={"file": ("chunk.webm", audio_bytes, content_type)},
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
