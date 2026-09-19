"""Backboard = the stateful coaching layer around Gemini.

Backboard is *not* a decorative extra API here. It is the persistent coaching
brain that wraps Gemini:

    Assistant  = the user's long-term speaking coach   (one per Heard user)
    Thread     = one practice / presentation session    (Speech.backboard_thread_id)
    Message    = one 60-second transcript segment        (RealtimeSegment)

Memories are stored at the *assistant* level and shared across that assistant's
threads, so session 3 can draw on what the coach learned in sessions 1 and 2.
Each Heard user gets their **own** assistant so coaching memory is never mixed
between users.

Gemini stays the model that actually produces the coaching — we route through
Backboard with ``llm_provider="google"`` — while Backboard supplies the
persistent state, cross-session memory and tool calling around it:

              ┌── Backboard thread   (this session's ordered history)
  Transcript → Backboard ── Backboard memory (past sessions' patterns/goals)
              └── Google / Gemini    (reasoning + structured feedback)
                        ↓
                     Feedback

Memory usage is deliberately split:
  * during the session   → ``memory="Readonly"``  (retrieve, don't write garbage)
  * when the session ends → ``memory="Auto"``      (extract durable coaching memories)

No-key fallback: if ``BACKBOARD_API_KEY`` is unset we return deterministic stub
coaching so the whole pipeline still runs end-to-end in local dev / tests.

Docs: https://docs.backboard.io
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models import Speech, SpeechMetrics, User

logger = logging.getLogger("heard.backboard")


# ─────────────────────────────────────────────────────────────────────────────
# Coach persona + memory prompts (configured once, at assistant creation)
# ─────────────────────────────────────────────────────────────────────────────

COACH_SYSTEM_PROMPT = """\
You are Heard, an adaptive communication coach.

Your job is not to rewrite the user's presentation for them.
Your job is to train the user to become a stronger communicator over time.

During live practice:
- Analyze the current presentation segment.
- Consider the earlier segments from this practice session.
- Consider relevant memories from previous practice sessions.
- Identify the single highest-impact improvement the speaker can make next.
- Prefer specific evidence over generic advice.
- Do not overwhelm the speaker with multiple corrections.
- Recognize genuine improvement from previous sessions.
- Do not infer internal confidence or personality from transcript text.
- Focus on observable communication behavior.

Evaluate: clarity, structure, concision, specificity, persuasiveness,
filler/hedging language, repetition, domain appropriateness, strength of
claims, transitions, and call-to-action quality.

Feedback should help the speaker improve during the NEXT minute, not merely
describe what was wrong in the previous minute.

When you need concrete performance history (exact past scores, filler rates,
trends), call the get_recent_performance tool rather than guessing.

ALWAYS reply with ONLY a JSON object of this exact shape, no prose, no code
fences:
{
  "focus_area": "one of: clarity | structure | concision | specificity | persuasiveness | pace | confidence",
  "nudge": "<=12 words, the single live recommendation for the next minute",
  "evidence": "one short sentence citing what in this segment prompted the nudge",
  "progress": "one short sentence on change vs earlier segments/sessions, or \\"\\"",
  "next_minute_goal": "one concrete thing to do in the next minute",
  "scores": {"clarity": 0, "structure": 0, "concision": 0, "persuasiveness": 0}
}
Scores are integers 0-100."""

FACT_EXTRACTION_PROMPT = """\
Only save durable information useful for future communication coaching.

Good memories include:
- recurring speaking patterns
- persistent weaknesses
- demonstrated strengths
- the user's communication goals
- presentation domain preferences
- improvements across multiple sessions
- previously assigned coaching goals
- strategies that worked for this user

Do NOT save:
- entire transcripts
- incidental facts mentioned inside a presentation
- one-time mistakes
- sensitive personal information
- generic facts unrelated to communication training

Prefer "User tends to bury the main claim after long context."
over   "On September 19 the user said..."."""

UPDATE_MEMORY_PROMPT = """\
Update existing communication-skill memories rather than creating duplicates.

When new evidence contradicts an old performance pattern, update the old memory.
Track progression when useful.

Example:
Old: "User frequently uses hedging language."
New evidence after repeated sessions:
"User previously used frequent hedging language but has significantly reduced it."."""


# The assistant's one custom tool: pull exact performance history from our DB
# (Backboard memory is great for patterns, but the DB is the source of truth
# for precise analytics). Later this can query TigerData instead of SQLite.
PERFORMANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_recent_performance",
        "description": (
            "Get the user's exact scores from their most recent completed "
            "practice sessions (clarity, structure, confidence, pace, volume, "
            "overall). Use for precise numbers and trends instead of guessing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many recent sessions to return (default 5).",
                }
            },
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Client (lazy, cached) — None means "no key → stub mode"
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _client():
    if not settings.backboard_api_key:
        return None
    try:
        from backboard import BackboardClient
    except ImportError:  # SDK not installed — degrade to stub rather than crash
        logger.warning("backboard-sdk not installed; running coaching in stub mode")
        return None
    return BackboardClient(api_key=settings.backboard_api_key)


def enabled() -> bool:
    """True when a real Backboard client is available."""
    return _client() is not None


# ─────────────────────────────────────────────────────────────────────────────
# Assistant lifecycle — one persistent coach per Heard user
# ─────────────────────────────────────────────────────────────────────────────

async def ensure_assistant(user_id: str) -> str | None:
    """Return this user's Backboard assistant id, creating it on first use.

    Returns None in stub mode (no key) so callers fall back to stub coaching.
    """
    client = _client()
    if client is None:
        return None

    with Session(engine) as session:
        user = session.get(User, user_id)
        if user and user.backboard_assistant_id:
            return user.backboard_assistant_id

    try:
        assistant = await client.create_assistant(
            name=f"heard-coach-{user_id}",
            system_prompt=COACH_SYSTEM_PROMPT,
            custom_fact_extraction_prompt=FACT_EXTRACTION_PROMPT,
            custom_update_memory_prompt=UPDATE_MEMORY_PROMPT,
            tools=[PERFORMANCE_TOOL],
        )
    except Exception:
        logger.exception("failed to create Backboard assistant for %s", user_id)
        return None

    assistant_id = getattr(assistant, "assistant_id", None)
    if not assistant_id:
        return None

    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            user.backboard_assistant_id = assistant_id
            session.add(user)
            session.commit()
    return assistant_id


# ─────────────────────────────────────────────────────────────────────────────
# Live coaching — one 60s segment → one structured intervention
# ─────────────────────────────────────────────────────────────────────────────

async def coach_segment(
    user_id: str,
    assistant_id: str | None,
    thread_id: str | None,
    transcript: str,
    segment_index: int,
) -> tuple[dict, str | None]:
    """Coach one 60-second segment.

    Retrieves cross-session memory (Readonly) + this thread's earlier minutes,
    runs Gemini through Backboard, resolves any get_recent_performance tool
    calls, and returns ``(feedback_dict, thread_id)``. ``thread_id`` is the
    (possibly newly created) session thread to persist on the Speech.
    """
    client = _client()
    if client is None or assistant_id is None:
        return _stub_feedback(transcript, segment_index), thread_id

    prompt = (
        f"This is minute {segment_index + 1} of the user's live practice.\n\n"
        f"CURRENT TRANSCRIPT:\n{transcript}\n\n"
        "Give one high-impact coaching intervention for the next minute. "
        "Return ONLY the JSON object described in your instructions."
    )

    kwargs: dict = {
        "llm_provider": "google",
        "model_name": settings.backboard_google_model,
        "memory": "Readonly",   # retrieve past memories, don't write per-minute noise
        "stream": False,
    }
    if thread_id:
        kwargs["thread_id"] = thread_id
    else:
        kwargs["assistant_id"] = assistant_id

    try:
        response = await client.send_message(prompt, **kwargs)
        thread_id = getattr(response, "thread_id", None) or thread_id
        response = await _resolve_tool_calls(client, response, thread_id, user_id)
        content = getattr(response, "content", "") or ""
        return _parse_feedback(content, transcript, segment_index), thread_id
    except Exception:
        logger.exception("Backboard coach_segment failed (seg %s)", segment_index)
        return _stub_feedback(transcript, segment_index), thread_id


async def _resolve_tool_calls(client, response, thread_id: str | None, user_id: str):
    """Loop until the model stops requesting tools (get_recent_performance)."""
    guard = 0
    while (
        getattr(response, "status", None) == "REQUIRES_ACTION"
        and getattr(response, "tool_calls", None)
        and guard < 4
    ):
        guard += 1
        outputs = []
        for call in response.tool_calls:
            name = call.function.name
            args = getattr(call.function, "parsed_arguments", None) or {}
            result = _dispatch_tool(name, args, user_id)
            outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})
        response = await client.submit_tool_outputs_simple(
            thread_id=thread_id,
            tool_outputs=outputs,
        )
    return response


def _dispatch_tool(name: str, args: dict, user_id: str) -> dict:
    if name == "get_recent_performance":
        return get_recent_performance(user_id, limit=int(args.get("limit", 5) or 5))
    return {"error": f"Unknown tool: {name}"}


# ─────────────────────────────────────────────────────────────────────────────
# End of session — extract durable memories (Auto)
# ─────────────────────────────────────────────────────────────────────────────

async def finalize_session(
    assistant_id: str | None,
    thread_id: str | None,
    summary: str,
) -> None:
    """One ``memory="Auto"`` call at session end so Backboard extracts durable,
    communication-specific memories for future sessions."""
    client = _client()
    if client is None or assistant_id is None:
        return

    kwargs: dict = {
        "llm_provider": "google",
        "model_name": settings.backboard_google_model,
        "memory": "Auto",   # now we WANT it to write long-term memories
        "stream": False,
    }
    if thread_id:
        kwargs["thread_id"] = thread_id
    else:
        kwargs["assistant_id"] = assistant_id

    try:
        await client.send_message(summary, **kwargs)
    except Exception:
        logger.exception("Backboard finalize_session failed")


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementation — exact performance history from the DB
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_performance(user_id: str, limit: int = 5) -> dict:
    """Return the user's most recent completed-session scores (newest first)."""
    limit = max(1, min(limit, 20))
    with Session(engine) as session:
        rows = session.exec(
            select(SpeechMetrics, Speech)
            .join(Speech, SpeechMetrics.speech_id == Speech.id)
            .where(Speech.user_id == user_id)
            .order_by(Speech.started_at.desc())
            .limit(limit)
        ).all()

    sessions = [
        {
            "clarity": m.clarity,
            "structure": m.structure,
            "confidence": m.confidence,
            "pace": m.pace,
            "volume": m.volume,
            "overall": m.overall,
        }
        for m, _ in rows
    ]
    return {"last_5_sessions": sessions}


# ─────────────────────────────────────────────────────────────────────────────
# Feedback parsing + stub fallback
# ─────────────────────────────────────────────────────────────────────────────

_STUB_NUDGES = [
    "State your main point before the background.",
    "Trim the filler — pause instead of saying 'um'.",
    "Add one concrete example to back that claim.",
    "Signal your transition: 'Which brings me to...'.",
    "Close this section with a clear takeaway.",
]


def _stub_feedback(transcript: str, segment_index: int) -> dict:
    """Deterministic no-key coaching so the pipeline runs without an API key."""
    nudge = _STUB_NUDGES[segment_index % len(_STUB_NUDGES)]
    return {
        "focus_area": "structure",
        "nudge": nudge,
        "evidence": "Stub coaching — set BACKBOARD_API_KEY for adaptive feedback.",
        "progress": "",
        "next_minute_goal": nudge,
        "scores": {"clarity": 72, "structure": 68, "concision": 70, "persuasiveness": 69},
    }


def _parse_feedback(content: str, transcript: str, segment_index: int) -> dict:
    """Parse the model's JSON, tolerating code fences / stray prose."""
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # Fall back to the first {...} block if the model added prose around it.
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        fallback = _stub_feedback(transcript, segment_index)
        # Preserve whatever the model said as the live nudge if it's short.
        one_line = " ".join(content.split())[:120]
        if one_line:
            fallback["nudge"] = one_line
            fallback["evidence"] = ""
        return fallback

    # Normalise shape so downstream/DB always sees the same keys.
    data.setdefault("focus_area", "structure")
    data.setdefault("nudge", "")
    data.setdefault("evidence", "")
    data.setdefault("progress", "")
    data.setdefault("next_minute_goal", "")
    data.setdefault("scores", {})
    if not isinstance(data.get("scores"), dict):
        data["scores"] = {}
    data["nudge"] = str(data["nudge"])[:120]
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Utility — list the Google/Gemini models Backboard currently supports
# ─────────────────────────────────────────────────────────────────────────────

async def list_google_models() -> list:
    """Query Backboard for currently supported Google models.

    Handy for choosing/updating BACKBOARD_GOOGLE_MODEL. Returns [] in stub mode.
    """
    if not settings.backboard_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{settings.backboard_base_url}/models/provider/google",
                headers={"X-API-Key": settings.backboard_api_key},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("failed to list Backboard google models")
        return []
