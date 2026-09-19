"""AI coach adapter — Backboard→Gemini coaching + strict longitudinal schema.

All coaching flows (pre-training, post-training analysis, follow-up chat) route
through the EXISTING Backboard integration (``services.backboard``), which wraps
Gemini and supplies persistent per-user assistants + threads. There is no
separate direct Gemini SDK call in this module.

Historical context is never left to "hidden" Backboard memory alone: every call
is handed an explicit, Supabase-sourced context packet (built by
``services.context_builder``). Backboard adds continuity; Supabase is canonical.

When no Backboard key is configured (or a call fails), we fall back to a rich
DETERMINISTIC analysis derived from the objective metrics so the pipeline always
completes offline / in tests.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services import backboard

logger = logging.getLogger("heard.ai_coach")


# ─────────────────────────────────────────────────────────────────────────────
# Strict structured analysis schema (requirement 23)
# ─────────────────────────────────────────────────────────────────────────────

def _bounded(v):
    if v is None:
        return v
    if not (0 <= v <= 100):
        raise ValueError("score must be between 0 and 100")
    return round(float(v), 2)


class Scores(BaseModel):
    clarity: Optional[float] = None
    conciseness: Optional[float] = None
    pace: Optional[float] = None
    volume: Optional[float] = None          # null when no audio metrics
    confidence: Optional[float] = None
    structure: Optional[float] = None

    @field_validator("clarity", "conciseness", "pace", "volume", "confidence", "structure")
    @classmethod
    def _bound(cls, v):
        return _bounded(v)


class Moment(BaseModel):
    segment_index: Optional[int] = None
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    reason: str = ""
    evidence: str = ""


class PriorityMoment(Moment):
    dimension: str = ""
    recommendation: str = ""


class DimensionChange(BaseModel):
    dimension: str
    previous: Optional[float] = None
    current: Optional[float] = None
    explanation: str = ""
    evidence: str = ""


class Pattern(BaseModel):
    pattern: str
    sessions_observed: Optional[int] = None
    trend: str = "stable"  # improving | stable | worsening
    explanation: str = ""


class Goal(BaseModel):
    goal: str
    reason: str = ""
    measurement: str = ""


class MetricsInterpretation(BaseModel):
    pace: str = ""
    volume: str = ""
    pitch: str = ""
    pauses: str = ""
    fillers: str = ""
    hedging: str = ""


class HistoricalSummary(BaseModel):
    baseline_overall_score: Optional[float] = None
    previous_overall_score: Optional[float] = None
    current_overall_score: Optional[float] = None
    improvement_from_baseline_percent: Optional[float] = None


class SessionAnalysis(BaseModel):
    scores: Scores
    overall_score: Optional[float] = None
    current_session_summary: str = ""
    strongest_moments: List[Moment] = Field(default_factory=list)
    priority_moments: List[PriorityMoment] = Field(default_factory=list)
    improvements_since_previous: List[DimensionChange] = Field(default_factory=list)
    regressions_since_previous: List[DimensionChange] = Field(default_factory=list)
    persistent_patterns: List[Pattern] = Field(default_factory=list)
    new_patterns: List[Pattern] = Field(default_factory=list)
    stable_strengths: List[str] = Field(default_factory=list)
    metrics_interpretation: MetricsInterpretation = Field(default_factory=MetricsInterpretation)
    top_3_next_session_goals: List[Goal] = Field(default_factory=list)
    historical_summary: HistoricalSummary = Field(default_factory=HistoricalSummary)


class AIAnalysisError(Exception):
    """Raised when the model cannot produce valid structured analysis."""


# ─────────────────────────────────────────────────────────────────────────────
# System prompts (requirements 20, 21, 26)
# ─────────────────────────────────────────────────────────────────────────────

PRE_TRAINING_SYSTEM_PROMPT = """\
You are Heard, a longitudinal communication coach. Your purpose is not generic
public-speaking tips.

You have access to: the user's current speaking goal, their channel/domain,
relevant previous sessions, historical scores, recurring strengths/weaknesses,
and previous coaching context.

FIRST understand: what they are speaking about, who the audience is, the outcome
they want, and the part they are worried about.

THEN connect preparation advice to their OWN historical behavior. Prefer
"During your previous {channel} session..." over "Speakers often...", when
historical evidence exists. Do not invent previous behavior. If history is
insufficient, behave as an initial-session coach.

Focus on actionable preparation: what to rehearse, where to slow down, how to
structure difficult sections, habits to watch for, likely questions, and one or
two MEASURABLE goals for the upcoming session. Avoid generic encouragement."""

POST_TRAINING_ANALYSIS_PROMPT = """\
You are Heard's longitudinal speech-performance analyst. You are NOT a generic
chatbot reviewing a transcript.

You are given a structured evidence packet: the CURRENT SESSION (transcript,
segments, timing, WPM, pauses, filler/hedging statistics, volume + pitch
measurements, sentence statistics) and HISTORICAL PERFORMANCE (previous session,
baseline, recent averages, historical scores, recurring observations).

Determine: what objectively happened; what improved vs this user's own previous
performance; what declined; which habits persist; what new pattern appeared;
which exact sections caused the biggest score changes; and the highest-value
things to practice next.

Rules:
- Never produce generic advice when user-specific evidence exists.
- Ground every important conclusion in transcript evidence and/or a specific
  metric (timing, pace, pause, filler/hedging, amplitude, pitch) and/or
  previous-session evidence.
- Cite exact segments/timestamps (e.g. "segment 3, 2:00-3:00").
- Distinguish OBSERVATION from INTERPRETATION from RECOMMENDATION.
- Score six dimensions 0-100: clarity, conciseness, pace, volume, confidence,
  structure. If NO audio metrics were supplied, set scores.volume to null and
  say volume could not be measured — never fabricate it. Speak of "relative
  volume consistency", never absolute loudness/decibels.
- Next-session goals MUST be measurable (e.g. "keep architecture segments below
  165 WPM", "reduce hedging from 6.2 to under 4 per 100 words").
- Do NOT infer emotion, personality, anxiety, or competence. You analyze
  measurements extracted from audio; you did not hear the user.
- Output ONLY valid JSON matching the provided schema. No prose, no code fences."""

POST_TRAINING_CHAT_PROMPT = """\
You are Heard, the user's communication coach. This conversation is attached to
a completed speaking session. You have the session transcript, objective speech
metrics, the session analysis, the user's prior sessions in this channel, and
longitudinal trends.

When asked WHY something happened, explain using actual evidence. When asked
WHETHER they improved, compare current and historical evidence. When asked HOW
to improve, give a targeted exercise tied to their observed behavior. Never
invent audio characteristics or past events. Never default to generic advice
when session-specific evidence exists."""


# ─────────────────────────────────────────────────────────────────────────────
# JSON schema hint appended to the analysis message
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_HINT = """\
{
  "scores": {"clarity":0,"conciseness":0,"pace":0,"volume":0,"confidence":0,"structure":0},
  "overall_score": 0,
  "current_session_summary": "",
  "strongest_moments": [{"segment_index":0,"timestamp_start":0,"timestamp_end":60,"reason":"","evidence":""}],
  "priority_moments": [{"segment_index":0,"timestamp_start":0,"timestamp_end":60,"dimension":"pace","reason":"","evidence":"","recommendation":""}],
  "improvements_since_previous": [{"dimension":"clarity","previous":70,"current":78,"explanation":"","evidence":""}],
  "regressions_since_previous": [],
  "persistent_patterns": [{"pattern":"","sessions_observed":3,"trend":"improving","explanation":""}],
  "new_patterns": [],
  "stable_strengths": [],
  "metrics_interpretation": {"pace":"","volume":"","pitch":"","pauses":"","fillers":"","hedging":""},
  "top_3_next_session_goals": [{"goal":"","reason":"","measurement":""}],
  "historical_summary": {"baseline_overall_score":null,"previous_overall_score":null,"current_overall_score":null,"improvement_from_baseline_percent":null}
}"""


# ─────────────────────────────────────────────────────────────────────────────
# Message builders
# ─────────────────────────────────────────────────────────────────────────────

def build_analysis_message(context: dict) -> str:
    return (
        POST_TRAINING_ANALYSIS_PROMPT
        + "\n\nEVIDENCE PACKET (JSON):\n"
        + json.dumps(context, ensure_ascii=False, default=str)
        + "\n\nReturn ONLY JSON in exactly this shape:\n"
        + _SCHEMA_HINT
    )


def build_pretraining_message(context: dict, user_message: str) -> str:
    return (
        PRE_TRAINING_SYSTEM_PROMPT
        + "\n\nUSER HISTORY & CONTEXT (JSON):\n"
        + json.dumps(context, ensure_ascii=False, default=str)
        + f"\n\nUSER MESSAGE:\n{user_message}"
    )


def build_posttraining_message(context: dict, user_message: str) -> str:
    return (
        POST_TRAINING_CHAT_PROMPT
        + "\n\nSESSION EVIDENCE & HISTORY (JSON):\n"
        + json.dumps(context, ensure_ascii=False, default=str)
        + f"\n\nUSER QUESTION:\n{user_message}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# High-level operations (Backboard-first, deterministic fallback)
# ─────────────────────────────────────────────────────────────────────────────

async def pretraining_reply(user_id: str, thread, context: dict, user_message: str) -> tuple[str, Optional[str]]:
    """Return (reply, backboard_thread_id) for a pre-training coaching turn."""
    if backboard.enabled():
        assistant_id = await backboard.ensure_coach_assistant(user_id)
        message = build_pretraining_message(context, user_message)
        content, tid = await backboard.generate(
            user_id, assistant_id, getattr(thread, "backboard_thread_id", None), message,
            memory="Readonly",
        )
        if content.strip():
            return content.strip(), tid
    return _stub_pretraining(context, user_message), getattr(thread, "backboard_thread_id", None)


async def posttraining_reply(user_id: str, thread, context: dict, user_message: str) -> tuple[str, Optional[str]]:
    """Return (reply, backboard_thread_id) for a post-training follow-up turn."""
    if backboard.enabled():
        assistant_id = await backboard.ensure_coach_assistant(user_id)
        message = build_posttraining_message(context, user_message)
        content, tid = await backboard.generate(
            user_id, assistant_id, getattr(thread, "backboard_thread_id", None), message,
            memory="Readonly",
        )
        if content.strip():
            return content.strip(), tid
    return _stub_posttraining(context, user_message), getattr(thread, "backboard_thread_id", None)


async def analyze_session(user_id: str, context: dict) -> SessionAnalysis:
    """Structured longitudinal analysis. Retries once on malformed JSON, then
    raises AIAnalysisError (caller marks the session FAILED cleanly)."""
    if not backboard.enabled():
        return _stub_analysis(context)

    assistant_id = await backboard.ensure_coach_assistant(user_id)
    if assistant_id is None:
        return _stub_analysis(context)

    message = build_analysis_message(context)
    raw = ""
    for attempt in range(2):
        try:
            # memory="Auto" at session end so Backboard extracts durable memories.
            raw, _ = await backboard.generate(user_id, assistant_id, None, message, memory="Auto")
            if not raw.strip():
                raise ValueError("empty response")
            return SessionAnalysis.model_validate_json(_extract_json(raw))
        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            logger.warning("analysis JSON invalid (attempt %s): %s", attempt + 1, e)
            message = (
                "Your previous reply was not valid JSON for the required schema. "
                f"Reply again with ONLY corrected JSON.\n\nPrevious reply:\n{raw}\n\n"
                + build_analysis_message(context)
            )
        except Exception:
            logger.exception("analysis provider call failed")
            break
    raise AIAnalysisError("Model did not return valid structured analysis.")


def _extract_json(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            t = t[start:end + 1]
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic fallbacks (no-key mode / provider failure)
# ─────────────────────────────────────────────────────────────────────────────

def _stub_analysis(context: dict) -> SessionAnalysis:
    evidence = context.get("current_session", {})
    det = evidence.get("deterministic_scores", {})
    lang = evidence.get("language", {})
    pace = evidence.get("pace", {})
    has_audio = evidence.get("has_audio_metrics", False)
    hist = context.get("historical", {})

    scores = Scores(
        clarity=72.0,
        conciseness=det.get("conciseness"),
        pace=det.get("pace"),
        volume=det.get("volume") if has_audio else None,
        confidence=det.get("confidence"),
        structure=70.0,
    )
    overall = _avg([scores.clarity, scores.conciseness, scores.pace,
                    scores.volume, scores.confidence, scores.structure])

    improvements, regressions = _stub_dimension_changes(scores, hist)

    summary = (
        f"Practice run at ~{pace.get('average_wpm')} WPM with a filler rate of "
        f"{lang.get('filler_rate')} per 100 words. "
        + ("No audio metrics were supplied, so volume was not measured. "
           if not has_audio else "")
        + "(Deterministic analysis — set BACKBOARD_API_KEY for full AI coaching.)"
    )

    goals = [
        Goal(goal="Reduce filler words",
             reason="Fillers interrupt meaning.",
             measurement=f"Bring filler rate below {max(3.0, (lang.get('filler_rate') or 0) - 1):.1f} per 100 words."),
        Goal(goal="Steady your pace",
             reason="Even pacing aids clarity.",
             measurement=f"Keep segments within {analysis_target_band()} WPM."),
        Goal(goal="Strengthen your conclusion",
             reason="Endings anchor the takeaway.",
             measurement="End with one summarizing sentence."),
    ]

    return SessionAnalysis(
        scores=scores,
        overall_score=overall,
        current_session_summary=summary,
        improvements_since_previous=improvements,
        regressions_since_previous=regressions,
        metrics_interpretation=MetricsInterpretation(
            pace=f"Average {pace.get('average_wpm')} WPM.",
            volume=("Relative volume consistency "
                    f"{evidence.get('volume', {}).get('consistency')}." if has_audio
                    else "No audio metrics supplied."),
            pitch="No pitch data." if not has_audio else "Pitch metrics recorded.",
            pauses="Pause data recorded." if has_audio else "No pause data.",
            fillers=f"{lang.get('filler_count')} fillers ({lang.get('filler_rate')}/100 words).",
            hedging=f"{lang.get('hedge_count')} hedging phrases ({lang.get('hedge_rate')}/100 words).",
        ),
        top_3_next_session_goals=goals,
        historical_summary=HistoricalSummary(
            baseline_overall_score=hist.get("baseline_overall_score"),
            previous_overall_score=hist.get("previous_overall_score"),
            current_overall_score=overall,
            improvement_from_baseline_percent=_pct(overall, hist.get("baseline_overall_score")),
        ),
    )


def analysis_target_band() -> str:
    from app.services.analysis import PACE_TARGET_MIN, PACE_TARGET_MAX
    return f"{PACE_TARGET_MIN}-{PACE_TARGET_MAX}"


def _stub_dimension_changes(scores: Scores, hist: dict):
    prev = (hist or {}).get("previous_scores") or {}
    improvements, regressions = [], []
    for dim in ["clarity", "conciseness", "pace", "volume", "confidence", "structure"]:
        cur = getattr(scores, dim)
        old = prev.get(dim)
        if cur is None or old is None:
            continue
        change = DimensionChange(dimension=dim, previous=old, current=cur,
                                 explanation=f"{dim} moved from {old} to {cur}.")
        if cur > old:
            improvements.append(change)
        elif cur < old:
            regressions.append(change)
    return improvements, regressions


def _stub_pretraining(context: dict, user_message: str) -> str:
    hist = context.get("performance_profile") or {}
    weaknesses = hist.get("recurring_weaknesses") or []
    channel = (context.get("channel") or {}).get("name", "this")
    if weaknesses:
        w = ", ".join(str(x) for x in weaknesses[:2])
        return (
            f"For your upcoming {channel} talk, focus on your recurring areas: {w}. "
            "Rehearse the hardest section one idea per sentence, and set one measurable "
            "goal (e.g. keep that section under 165 WPM). "
            "(Set BACKBOARD_API_KEY for full adaptive coaching.)"
        )
    return (
        f"Let's prepare your {channel} talk. Tell me your audience, your goal, and the "
        "part you're most worried about, and I'll build a focused rehearsal plan. "
        "(Set BACKBOARD_API_KEY for full adaptive coaching.)"
    )


def _stub_posttraining(context: dict, user_message: str) -> str:
    fb = (context.get("current_session") or {}).get("feedback") or {}
    overall = fb.get("overall_score")
    return (
        f"Based on this session (overall {overall}), the highest-value focus is reducing "
        "fillers in your densest section and keeping a steady pace. Ask me about any "
        "specific segment. (Set BACKBOARD_API_KEY for full adaptive coaching.)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Small numeric helpers
# ─────────────────────────────────────────────────────────────────────────────

def _avg(values: list) -> Optional[float]:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def _pct(current: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if current is None or baseline is None:
        return None
    return round(((current - baseline) / max(baseline, 1)) * 100, 2)
