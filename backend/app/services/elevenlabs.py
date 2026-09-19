"""ElevenLabs speech-to-text integration.

Two modes:
  1. transcribe_audio()      -> one-shot transcription of an uploaded audio blob.
  2. proxy_realtime_stt()    -> streaming: the extension side panel streams mic
     PCM over a WebSocket; we relay it to ElevenLabs Scribe realtime v2 and push
     transcript messages back. Without an API key, a stub streamer runs so the
     whole pipeline is testable end-to-end.

Docs: https://elevenlabs.io/docs/capabilities/speech-to-text
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger("heard.elevenlabs")

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


# ---------------------------------------------------------------------------
# Realtime streaming proxy
# ---------------------------------------------------------------------------
async def proxy_realtime_stt(client_ws) -> None:
    """Bridge the extension's audio WebSocket <-> ElevenLabs realtime STT.

    `client_ws` is a Starlette/FastAPI WebSocket that is already accepted.
    Protocol with the extension:
      - client -> server: first a JSON text frame {"type":"start","sample_rate":16000},
        then binary frames of 16kHz mono PCM (Int16 LE), then {"type":"stop"}.
      - server -> client: JSON frames {"type":"transcript","text":str,"is_final":bool}
        or {"type":"error","detail":str}.
    """
    if not settings.elevenlabs_api_key:
        await _stub_stream(client_ws)
        return

    try:
        await _elevenlabs_bridge(client_ws)
    except Exception as exc:  # keep the panel informed instead of a silent drop
        logger.exception("realtime STT bridge failed")
        await _safe_send(client_ws, {"type": "error", "detail": str(exc)})


async def _elevenlabs_bridge(client_ws) -> None:
    """Real path: relay audio to ElevenLabs and transcripts back.

    NOTE: confirm the exact realtime message schema against ElevenLabs' docs for
    Scribe v2 realtime; parsing below is intentionally defensive.
    """
    import websockets  # local import so the app boots even if not installed

    url = f"{settings.elevenlabs_stt_ws_url}?model_id={settings.elevenlabs_realtime_model}"
    headers = {"xi-api-key": settings.elevenlabs_api_key}

    async with websockets.connect(url, extra_headers=headers, max_size=None) as el_ws:

        async def pump_audio_to_el():
            while True:
                message = await client_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if (data := message.get("bytes")) is not None:
                    await el_ws.send(data)
                elif (text := message.get("text")) is not None:
                    payload = json.loads(text)
                    if payload.get("type") == "stop":
                        # Signal end-of-stream to ElevenLabs, then finish.
                        await el_ws.send(json.dumps({"type": "stop"}))
                        break

        async def pump_transcripts_to_client():
            async for raw in el_ws:
                parsed = _parse_el_message(raw)
                if parsed:
                    await _safe_send(client_ws, parsed)

        await asyncio.gather(pump_audio_to_el(), pump_transcripts_to_client())


def _parse_el_message(raw) -> dict | None:
    """Normalize an ElevenLabs realtime frame into our transcript schema."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    text = data.get("text") or data.get("transcript") or data.get("delta")
    if not text:
        return None
    is_final = bool(data.get("is_final") or data.get("final") or data.get("type") == "final")
    return {"type": "transcript", "text": text, "is_final": is_final}


async def _stub_stream(client_ws) -> None:
    """No-key fallback: emit a growing canned transcript so the UI/pipeline works.

    Drains incoming audio so the socket doesn't stall, and emits interim words
    that periodically 'finalize' — mimicking realtime partial results.
    """
    words = (
        "this is a stub transcript set ELEVENLABS_API_KEY in the backend "
        "env to hear your real words in real time".split()
    )
    built: list[str] = []
    i = 0
    try:
        while True:
            try:
                message = await asyncio.wait_for(client_ws.receive(), timeout=0.6)
                if message.get("type") == "websocket.disconnect":
                    break
                if (text := message.get("text")) is not None:
                    if json.loads(text).get("type") == "stop":
                        break
            except asyncio.TimeoutError:
                pass  # no audio this tick — still show progress

            built.append(words[i % len(words)])
            i += 1
            is_final = i % 7 == 0
            await _safe_send(
                client_ws,
                {"type": "transcript", "text": " ".join(built), "is_final": is_final},
            )
            if is_final:
                built = []
    except Exception:
        return


async def _safe_send(client_ws, payload: dict) -> None:
    try:
        await client_ws.send_json(payload)
    except Exception:
        pass
