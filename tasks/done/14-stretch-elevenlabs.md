# Task 14 — Stretch: ElevenLabs Transcription

**Status:** stretch — only if Web Speech API quality is insufficient  
**Owner:** backend/app/services/ + extension/

---

## Decision gate

Use Web Speech API (free, no quota) unless transcription quality is noticeably bad during testing. ElevenLabs adds cost and complexity — wire it only if needed.

---

## Flow (if wired)

```
Extension records audio → sends audio blob to backend
→ POST /api/speech/transcribe  { audio: base64, speech_id }
→ backend calls ElevenLabs Speech-to-Text
→ returns { transcript } → extension uses this instead of Web Speech API output
```

---

## Backend changes

New service `backend/app/services/elevenlabs.py`:
```python
def transcribe(audio_base64: str) -> str:
    if not os.getenv("ELEVENLABS_API_KEY"):
        return ""   # stub — caller falls back to Web Speech API output
    # call ElevenLabs STT API
    ...
```

New endpoint in speech router:
```
POST /api/speech/transcribe
Body: { audio: base64_string, speech_id: str }
Response: { transcript: str }
```

---

## Extension changes

In `background.js`, after each 2-min segment:
- If `ELEVENLABS_MODE=true` in config: POST audio blob to `/api/speech/transcribe` instead of using Web Speech API text directly
- Otherwise: use Web Speech API transcript as-is (current behavior)

---

## New env var
```
ELEVENLABS_API_KEY=<from elevenlabs.io>
```

Free tier: 10k characters/month. Each 2-min segment ≈ 300 words ≈ 1,500 chars → ~6 segments free/month. Not enough for real use — POC only.
