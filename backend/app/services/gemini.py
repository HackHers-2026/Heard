"""Google Gemini integration — the coaching brain of Heard.

Three jobs:
  1. live_feedback()  -> short, encouraging real-time tip for the extension pop-up
  2. summarize()      -> post-practice summary + score for the web app chat view
  3. pre_training()   -> domain-specific prep coaching before the user starts

Conversation memory is layered in via Backboard so feedback is aware of the
user's history. Falls back to deterministic stubs when GEMINI_API_KEY is unset.
"""
from __future__ import annotations

import json

from app.config import settings
from app.services import backboard

try:
    import google.generativeai as genai
except ImportError:  # keep import-safe if the dep isn't installed yet
    genai = None


def _model():
    if not settings.gemini_api_key or genai is None:
        return None
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model)


LIVE_SYSTEM = (
    "You are Heard, a warm, confidence-building public-speaking coach for women. "
    "Given a short chunk of a live pitch, respond with ONE concise, actionable, "
    "encouraging tip (max 20 words). Focus on filler words, pacing, hedging "
    "language, and confidence. Never be harsh."
)


async def live_feedback(thread_id: str | None, domain: str, chunk: str) -> dict:
    """Return {"feedback": str, "tip_category": str} for a transcript chunk."""
    model = _model()
    if model is None:
        return {
            "feedback": "Great pace — try replacing 'um' with a short pause for impact.",
            "tip_category": "filler-words",
        }

    history = await backboard.get_memory(thread_id) if thread_id else []
    context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    prompt = (
        f"{LIVE_SYSTEM}\nDomain: {domain}\nRecent context:\n{context}\n\n"
        f"Latest chunk: \"{chunk}\"\n"
        'Respond as JSON: {"feedback": "...", "tip_category": "..."}'
    )
    resp = await model.generate_content_async(prompt)
    return _safe_json(resp.text, {"feedback": resp.text.strip(), "tip_category": "clarity"})


async def summarize(thread_id: str | None, domain: str, transcript: str) -> dict:
    """Return a summary + score + strengths/improvements for the whole run."""
    model = _model()
    if model is None:
        return {
            "summary": "Solid, well-structured pitch. You sounded confident and stayed on topic. "
            "Watch a few filler words near the middle and land your closing statement harder.",
            "score": 78.0,
            "strengths": ["Clear structure", "Confident tone", "Good domain vocabulary"],
            "improvements": ["Reduce filler words", "Slow down transitions", "Stronger call to action"],
        }

    prompt = (
        "You are Heard, a supportive public-speaking coach for women. Evaluate this "
        f"{domain} pitch transcript. Return JSON with keys: summary (string, 2-3 "
        "sentences, encouraging but honest), score (0-100 number), strengths (list of "
        "strings), improvements (list of strings).\n\n"
        f"Transcript:\n{transcript}"
    )
    resp = await model.generate_content_async(prompt)
    return _safe_json(
        resp.text,
        {"summary": resp.text.strip(), "score": 70.0, "strengths": [], "improvements": []},
    )


async def pre_training(domain: str) -> dict:
    """Domain-specific prep coaching shown before the user starts practicing."""
    model = _model()
    if model is None:
        return {
            "coaching": f"Before your {domain} pitch: open with the problem, quantify the "
            "impact, then your solution. Speak in short, declarative sentences and "
            "own the room — you were invited here for a reason.",
            "checklist": [
                "State the problem in one sentence",
                "Back it with one number or fact",
                "Give your solution + why you",
                "End with a clear ask",
            ],
        }

    prompt = (
        f"Give pre-practice coaching for a woman about to pitch in the {domain} domain. "
        'Return JSON: {"coaching": "2-3 sentences", "checklist": ["...", "..."]}'
    )
    resp = await model.generate_content_async(prompt)
    return _safe_json(resp.text, {"coaching": resp.text.strip(), "checklist": []})


def _safe_json(text: str, fallback: dict) -> dict:
    """Gemini sometimes wraps JSON in ```; extract it defensively."""
    try:
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        return fallback
