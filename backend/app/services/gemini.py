import hashlib
import json
import os
import re
from functools import lru_cache

from sqlmodel import Session, select

from app.models import ChatMessage, RealtimeSegment, Speech, SpeechMetrics
from app.services import tigertable

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Filler words that signal low confidence
_FILLERS = re.compile(
    r"\b(um+|uh+|like|basically|sort of|kind of|you know|i mean|right\?|so+)\b",
    re.IGNORECASE,
)

# Target pace range (wpm)
_PACE_MIN, _PACE_MAX = 120, 150


def _stub_mode() -> bool:
    return not bool(GEMINI_KEY)


# ── Encourage ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _quick_stub() -> dict:
    return {"message": "Your idea is worth sharing — the room needs to hear it."}


def encourage(mode: str, context: str = None) -> dict:
    if _stub_mode() or mode == "quick":
        # quick encourage is always the same → cache it, never call API
        result = dict(_quick_stub())
        if mode == "plan":
            result["outline"] = [
                "Start with the problem you're solving",
                "Present your solution clearly",
                "End with a specific ask or call to action",
            ]
        return result

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Warm peer-level pep talk (1-2 sentences) + 3-point outline for: "
            f"{context or 'their topic'}. "
            'JSON only: {"message":"...","outline":["...","...","..."]}'
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(text)
    except Exception:
        result = dict(_quick_stub())
        result["outline"] = ["Start with the problem", "Present your solution", "End with a clear ask"]
        return result


# ── Nudge (uses flash-8b — half the quota cost) ───────────────────────────────

def nudge(transcript: str, avg_volume: int = 0, pace_wpm: int = 0) -> str | None:
    if _stub_mode():
        return "You're doing great, keep going"

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash-8b")
        prompt = (
            f'Speech chunk: "{transcript[:300]}". '
            f"Vol {avg_volume}/100, pace {pace_wpm}wpm (target 120-150). "
            "ONE nudge, ≤10 words, no quotes."
        )
        resp = model.generate_content(prompt)
        return resp.text.strip()[:80] or None
    except Exception:
        return "You're doing great, keep going"


# ── Score (hybrid: deterministic for 3 metrics, Gemini for 2) ────────────────

def score(speech_id: str, session: Session) -> None:
    existing = session.exec(
        select(SpeechMetrics).where(SpeechMetrics.speech_id == speech_id)
    ).first()
    if existing:
        return

    segs = session.exec(
        select(RealtimeSegment)
        .where(RealtimeSegment.speech_id == speech_id)
        .order_by(RealtimeSegment.segment_index)
    ).all()

    det = _deterministic_metrics(segs)

    if _stub_mode() or not segs:
        _save_metrics(
            speech_id, session,
            clarity=70, volume=det["volume"], pace=det["pace"],
            confidence=det["confidence"], structure=70,
            summary="Good effort. Keep building on your strengths.",
            suggestions='["Vary your pace", "Reduce filler words"]',
        )
        return

    # Only send clarity+structure to Gemini — much smaller prompt
    full_text = " ".join(s.transcript for s in segs)
    excerpt = full_text[:600]   # ~120 words max

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Rate this speech excerpt for clarity (sentence coherence, vocabulary) "
            f"and structure (detectable intro/body/conclusion). "
            f"Stats: pace={det['pace_wpm']}wpm, filler_rate={det['filler_pct']:.0f}%, "
            f"avg_volume={det['avg_volume']}/100.\n"
            f'Excerpt: "{excerpt}"\n'
            "JSON only — integers 0-100, 2-sentence summary, 2 suggestions:\n"
            '{"clarity":0,"structure":0,"summary":"...","suggestions":["...","..."]}'
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(text)

        _save_metrics(
            speech_id, session,
            clarity=int(data["clarity"]),
            volume=det["volume"],
            pace=det["pace"],
            confidence=det["confidence"],
            structure=int(data["structure"]),
            summary=data["summary"],
            suggestions=json.dumps(data["suggestions"]),
        )
    except Exception:
        _save_metrics(
            speech_id, session,
            clarity=70, volume=det["volume"], pace=det["pace"],
            confidence=det["confidence"], structure=70,
            summary="Good effort. Keep building on your strengths.",
            suggestions='["Work on sentence clarity", "Add a stronger closing"]',
        )


# ── Deterministic metrics (no LLM) ───────────────────────────────────────────

def _deterministic_metrics(segs: list) -> dict:
    if not segs:
        return {"volume": 70, "pace": 70, "confidence": 70,
                "pace_wpm": 130, "filler_pct": 0.0, "avg_volume": 65}

    # Volume — score avg_volume (0-100) with penalty for high variance
    avg_vol = sum(s.avg_volume for s in segs) / len(segs)
    avg_var = sum(s.volume_variance for s in segs) / len(segs)
    # Ideal: avg_volume 55-80, variance < 10
    vol_base = _range_score(avg_vol, low=45, ideal_low=55, ideal_high=80, high=95)
    var_penalty = min(20, int(avg_var / 2))
    volume_score = max(0, vol_base - var_penalty)

    # Pace — total words / total minutes
    total_words = sum(len(s.transcript.split()) for s in segs)
    total_mins = sum(s.duration_seconds for s in segs) / 60
    pace_wpm = int(total_words / total_mins) if total_mins > 0 else 130
    pace_score = _range_score(pace_wpm, low=80, ideal_low=_PACE_MIN,
                               ideal_high=_PACE_MAX, high=200)

    # Confidence — filler word density
    full_text = " ".join(s.transcript for s in segs)
    filler_count = len(_FILLERS.findall(full_text))
    filler_pct = (filler_count / max(total_words, 1)) * 100
    # 0% fillers = 100, 5% = 80, 10% = 60, 20%+ = 20
    confidence_score = max(20, int(100 - filler_pct * 4))

    return {
        "volume": int(volume_score),
        "pace": int(pace_score),
        "confidence": int(confidence_score),
        "pace_wpm": pace_wpm,
        "filler_pct": filler_pct,
        "avg_volume": int(avg_vol),
    }


def _range_score(val: float, low: float, ideal_low: float,
                 ideal_high: float, high: float) -> int:
    """Map a value to 0-100 based on an ideal range."""
    if ideal_low <= val <= ideal_high:
        return 100
    if val < ideal_low:
        if val <= low:
            return 20
        return int(20 + 80 * (val - low) / (ideal_low - low))
    # val > ideal_high
    if val >= high:
        return 20
    return int(100 - 80 * (val - ideal_high) / (high - ideal_high))


# ── Chat (phased, with memory) ────────────────────────────────────────────────

_PHASE_CONTEXT = {
    "preptalk":    "You are a warm speech coach helping the user prepare. Be encouraging and specific.",
    "activetalk":  "You are a real-time coach. Be terse — one nudge, 15 words max.",
    "talksummary": "You are a reflective coach reviewing a completed speech. Be growth-focused and kind.",
}

_PHASE_STUBS = {
    "preptalk":    "You're ready — start strong and own the room.",
    "activetalk":  "Slow down slightly, you're doing great.",
    "talksummary": "Strong structure. Work on reducing filler words next time.",
}


def make_session_hash(speech_id: str) -> str:
    return hashlib.sha256(speech_id.encode()).hexdigest()[:16]


def chat(speech_id: str, message: str, phase: str, session: Session) -> dict:
    session_hash = make_session_hash(speech_id)

    raw = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_hash == session_hash)
        .order_by(ChatMessage.created_at)
    ).all()
    # last 10 rows = last 5 exchanges
    history = [
        {"role": r.role, "parts": [r.content]}
        for r in raw[-10:]
    ]

    if _stub_mode():
        reply = _PHASE_STUBS.get(phase, "Keep going, you've got this.")
        summary = _stub_summary(message)
    else:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                system_instruction=_PHASE_CONTEXT.get(phase, _PHASE_CONTEXT["preptalk"]),
            )
            chat_session = model.start_chat(history=history)
            reply = chat_session.send_message(message).text.strip()
            summary = _generate_summary(message, reply)
        except Exception:
            reply = _PHASE_STUBS.get(phase, "Keep going, you've got this.")
            summary = _stub_summary(message)

    for role, content in [("user", message), ("model", reply)]:
        session.add(ChatMessage(
            session_hash=session_hash,
            speech_id=speech_id,
            role=role,
            phase=phase,
            content=content,
            summary=summary,
        ))
    session.commit()

    return {"reply": reply, "phase": phase, "summary": summary}


def _generate_summary(user_msg: str, model_reply: str) -> str:
    if _stub_mode():
        return _stub_summary(user_msg)
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash-8b")
        prompt = (
            f'User: "{user_msg[:100]}"\nReply: "{model_reply[:100]}"\n'
            "Summarise this exchange in 3-5 words. No punctuation. Lowercase."
        )
        return model.generate_content(prompt).text.strip()[:40]
    except Exception:
        return _stub_summary(user_msg)


def _stub_summary(text: str) -> str:
    return " ".join(text.split()[:4]).lower().rstrip("?.!")


# ── Shared save helper ────────────────────────────────────────────────────────

def _save_metrics(speech_id, session, clarity, volume, pace,
                  confidence, structure, summary, suggestions):
    overall = (clarity + volume + pace + confidence + structure) // 5
    metrics = SpeechMetrics(
        speech_id=speech_id,
        clarity=clarity, volume=volume, pace=pace,
        confidence=confidence, structure=structure,
        overall=overall,
        summary=summary,
        suggestions=suggestions,
    )
    session.add(metrics)
    speech = session.get(Speech, speech_id)
    if speech:
        speech.status = "done"
        session.add(speech)
    session.commit()

    tigertable.track("speech.ended", {
        "speech_id": speech_id,
        "user_id": speech.user_id if speech else None,
        "overall": overall,
        "clarity": clarity,
        "volume": volume,
        "pace": pace,
        "confidence": confidence,
        "structure": structure,
    })
