# Task 11 — Stretch: Chat Session Memory (Backboard)

**Status:** stretch — after core flows work  
**Owner:** backend/app/services/gemini.py + new ChatSession model  
**Reads:** https://docs.backboard.io

---

## Problem

Right now every Gemini call is stateless. The "encourage" and "nudge" endpoints have no memory of what was said earlier in the session — each call is cold. Users asking follow-up questions get disconnected responses.

---

## Two options

### Option A — Store locally in DB (no new service)
Keep a `ChatMessage` table: `(id, speech_id, role, content, created_at)`.
On each Gemini call, fetch the last N messages and prepend them as conversation history via `model.start_chat(history=[...])`.

**Pros:** no new keys, works offline, queryable.  
**Cons:** larger prompts → more quota. Cap at last 5 exchanges.

### Option B — Backboard (managed session memory)
Backboard wraps Gemini with persistent session memory across calls. Pass a `session_id` and it maintains context server-side.

**Pros:** cleaner code, no DB schema change.  
**Cons:** needs `BACKBOARD_API_KEY`, external service.

---

## Recommended for hackathon: Option A (DB local)

Fastest to ship. No new keys needed.

---

## Implementation (Option A)

### New model
```python
class ChatMessage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    speech_id: str = Field(foreign_key="speech.id")
    role: str           # "user" | "model"
    content: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
```

### New endpoint
```
POST /api/speech/{speech_id}/chat
Body: { "message": "Can you help me improve my opening?" }
Response: { "reply": "..." }
```

### gemini.py — chat()
```python
def chat(speech_id, user_message, session):
    history = fetch_last_5_messages(speech_id, session)
    model = genai.GenerativeModel("gemini-1.5-flash")
    chat = model.start_chat(history=history)
    reply = chat.send_message(user_message).text
    save_messages(speech_id, user_message, reply, session)
    return reply
```

History prompt budget: ~5 exchanges × ~100 tokens = ~500 tokens overhead per call — well within free quota.

---

## If using Backboard instead
```python
import backboard
backboard.configure(api_key=os.getenv("BACKBOARD_API_KEY"))
session = backboard.Session(id=speech_id)
reply = session.send(user_message, model="gemini-1.5-flash")
```

Add `BACKBOARD_API_KEY` to `.env`.
