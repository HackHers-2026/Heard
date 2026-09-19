"""Deterministic speech analysis + the single source of truth for scoring config.

This module turns raw transcript segments + frontend audio metrics into an
objective SESSION EVIDENCE PACKET. Everything here is computed WITHOUT an LLM;
Gemini (through Backboard) later *interprets* this evidence in context.

Honesty rules baked in:
  * Missing audio metrics are never invented. Volume/pitch/pause aggregates are
    ``None`` when the frontend didn't send them, and volume_score stays ``None``.
  * Raw metrics are evidence, not verdicts. We compute deterministic *starting*
    scores for pace/confidence/conciseness/volume, but the AI produces the final
    clarity/structure judgments and may adjust the others using context.

The six-dimension weighting lives in ``WEIGHTS`` — tune scoring in one place.
"""
from __future__ import annotations

import re
from statistics import mean, median, pstdev
from typing import Iterable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Scoring configuration (tune here, nowhere else)
# ─────────────────────────────────────────────────────────────────────────────

DIMENSIONS = ["clarity", "conciseness", "pace", "volume", "confidence", "structure"]

# Equal weighting. Change to re-weight the composite score.
WEIGHTS = {
    "clarity": 1.0,
    "conciseness": 1.0,
    "pace": 1.0,
    "volume": 1.0,
    "confidence": 1.0,
    "structure": 1.0,
}

# Comfortable presentation pace (words per minute).
PACE_TARGET_MIN = 120
PACE_TARGET_MAX = 160
PACE_FLOOR = 70
PACE_CEIL = 210

# Single-word fillers (always counted).
FILLER_WORDS = {"um", "umm", "uh", "uhh", "erm", "ah", "hmm", "mmm", "er"}
FILLER_WORDS_SOFT = {"basically", "actually", "literally"}  # discourse fillers

# Multi-word filler / discourse phrases.
FILLER_PHRASES = ["you know", "i mean"]

# Hedging (uncertainty) — tracked SEPARATELY from fillers.
HEDGE_WORDS = {"maybe", "probably", "perhaps", "possibly"}
HEDGE_PHRASES = [
    "i think", "i guess", "i feel like", "sort of", "kind of", "kinda", "sorta",
    "it might be", "it could be", "more or less", "i suppose",
]

# Transitions / discourse structure signals.
TRANSITION_PHRASES = [
    "first", "second", "third", "next", "then", "finally", "in conclusion",
    "to summarize", "in summary", "for example", "for instance", "however",
    "therefore", "as a result", "on the other hand", "which brings me to",
    "let me", "moving on", "to begin", "in short", "overall",
]

# Words that, when they follow "like", signal real usage rather than filler.
_LIKE_NON_FILLER_FOLLOWERS = {
    "a", "an", "the", "this", "that", "these", "those", "it", "you", "me",
    "him", "her", "them", "us", "my", "your", "our", "their", "his", "its",
    "to", "and",
}

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SENT_RE = re.compile(r"[.!?]+")


# ─────────────────────────────────────────────────────────────────────────────
# Word / timing helpers
# ─────────────────────────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def wpm(words: int, duration_seconds: Optional[float]) -> Optional[float]:
    if not duration_seconds or duration_seconds <= 0:
        return None
    return round(words / (duration_seconds / 60.0), 2)


def sentence_count(text: str) -> int:
    parts = [p for p in _SENT_RE.split(text or "") if p.strip()]
    return max(1, len(parts)) if (text or "").strip() else 0


# ─────────────────────────────────────────────────────────────────────────────
# Language statistics (fillers, hedges, repetition, transitions, questions)
# ─────────────────────────────────────────────────────────────────────────────

def language_stats(text: str) -> dict:
    lowered = (text or "").lower()
    tokens = _WORD_RE.findall(lowered)
    total = len(tokens)

    filler_count = 0
    hedge_count = 0
    filler_breakdown: dict[str, int] = {}
    hedge_breakdown: dict[str, int] = {}

    for i, tok in enumerate(tokens):
        if tok in FILLER_WORDS or tok in FILLER_WORDS_SOFT:
            filler_count += 1
            filler_breakdown[tok] = filler_breakdown.get(tok, 0) + 1
        elif tok in HEDGE_WORDS:
            hedge_count += 1
            hedge_breakdown[tok] = hedge_breakdown.get(tok, 0) + 1
        elif tok == "like":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt not in _LIKE_NON_FILLER_FOLLOWERS:
                filler_count += 1
                filler_breakdown["like"] = filler_breakdown.get("like", 0) + 1

    for phrase in FILLER_PHRASES:
        n = lowered.count(phrase)
        if n:
            filler_count += n
            filler_breakdown[phrase] = filler_breakdown.get(phrase, 0) + n
    for phrase in HEDGE_PHRASES:
        n = lowered.count(phrase)
        if n:
            hedge_count += n
            hedge_breakdown[phrase] = hedge_breakdown.get(phrase, 0) + n

    transition_count = sum(lowered.count(p) for p in TRANSITION_PHRASES)
    question_count = (text or "").count("?")
    sentences = sentence_count(text)
    avg_words_per_sentence = round(total / sentences, 2) if sentences else 0.0

    # Repetition: repeated 3-grams and unique-word ratio.
    repeated_phrase_count = _repeated_ngrams(tokens, n=3)
    unique_ratio = round(len(set(tokens)) / total, 3) if total else 1.0
    repeated_word_ratio = round(1 - unique_ratio, 3)

    return {
        "total_words": total,
        "sentence_count": sentences,
        "average_words_per_sentence": avg_words_per_sentence,
        "filler_count": filler_count,
        "filler_rate": round(filler_count / total * 100, 2) if total else 0.0,
        "filler_breakdown": filler_breakdown,
        "hedge_count": hedge_count,
        "hedge_rate": round(hedge_count / total * 100, 2) if total else 0.0,
        "hedge_breakdown": hedge_breakdown,
        "question_count": question_count,
        "transition_phrase_count": transition_count,
        "repeated_phrase_count": repeated_phrase_count,
        "repeated_word_ratio": repeated_word_ratio,
    }


def _repeated_ngrams(tokens: list[str], n: int = 3) -> int:
    if len(tokens) < n:
        return 0
    seen: dict[tuple, int] = {}
    for i in range(len(tokens) - n + 1):
        g = tuple(tokens[i:i + n])
        seen[g] = seen.get(g, 0) + 1
    return sum(1 for c in seen.values() if c > 1)


# Backwards-compatible helper (older callers / tests).
def count_fillers(text: str) -> dict:
    s = language_stats(text)
    return {
        "filler_count": s["filler_count"],
        "filler_rate": s["filler_rate"],
        "breakdown": s["filler_breakdown"],
        "total_words": s["total_words"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Audio-metric aggregation (None-safe — never fabricated)
# ─────────────────────────────────────────────────────────────────────────────

def _vals(metrics: list[dict], key: str) -> list[float]:
    out = []
    for m in metrics:
        v = m.get(key)
        if v is not None:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                pass
    return out


def volume_consistency(audio_metrics: Iterable[dict]) -> Optional[float]:
    """0-100 relative-consistency score from RMS variability + silence ratio."""
    metrics = [m for m in audio_metrics if isinstance(m, dict) and m]
    if not metrics:
        return None

    # Prefer explicit std-dev; fall back to legacy rms_variance.
    stds = _vals(metrics, "rms_std_dev") or _vals(metrics, "rms_variance")
    means = _vals(metrics, "average_rms")
    silences = _vals(metrics, "silence_ratio")
    if not stds and not silences:
        return None

    if stds and means:
        avg_mean = mean(means) or 1e-6
        cv = mean(stds) / avg_mean  # coefficient of variation
        var_penalty = min(60.0, cv * 120.0)
    elif stds:
        var_penalty = min(60.0, mean(stds) * 400.0)
    else:
        var_penalty = 0.0

    avg_silence = mean(silences) if silences else 0.0
    silence_penalty = min(40.0, max(0.0, avg_silence - 0.15) * 100.0)

    return round(max(0.0, 100.0 - var_penalty - silence_penalty), 2)


def aggregate_audio(segments: list) -> dict:
    """Aggregate volume / pitch / pause metrics across segments (None-safe)."""
    metrics = [getattr(s, "audio_metrics", None) or {} for s in segments]
    present = [m for m in metrics if m]
    has_audio = bool(present)

    def agg(key, fn=mean):
        vals = _vals(present, key)
        return round(fn(vals), 3) if vals else None

    # Segment-to-segment pitch drift (variability across segments' mean pitch).
    seg_pitch_means = _vals(present, "pitch_mean_hz")
    pitch_seg_variation = round(pstdev(seg_pitch_means), 2) if len(seg_pitch_means) > 1 else None

    pmin = min(_vals(present, "pitch_min_hz")) if _vals(present, "pitch_min_hz") else None
    pmax = max(_vals(present, "pitch_max_hz")) if _vals(present, "pitch_max_hz") else None
    pitch_range = round(pmax - pmin, 2) if (pmin is not None and pmax is not None) else None

    return {
        "has_audio_metrics": has_audio,
        "volume": {
            "average_rms": agg("average_rms"),
            "peak_rms": max(_vals(present, "peak_rms")) if _vals(present, "peak_rms") else None,
            "rms_variability": agg("rms_std_dev") or agg("rms_variance"),
            "silence_ratio": agg("silence_ratio"),
            "consistency": volume_consistency(present),
        },
        "pitch": {
            "mean_hz": agg("pitch_mean_hz"),
            "min_hz": pmin,
            "max_hz": pmax,
            "range_hz": pitch_range,
            "std_dev_hz": agg("pitch_std_dev_hz"),
            "segment_variation_hz": pitch_seg_variation,
        },
        "pauses": {
            "total_pause_count": int(sum(_vals(present, "long_pause_count"))) if _vals(present, "long_pause_count") else None,
            "long_pause_count": int(sum(_vals(present, "long_pause_count"))) if _vals(present, "long_pause_count") else None,
            "average_pause_ms": agg("average_pause_ms"),
            "max_pause_ms": max(_vals(present, "max_pause_ms")) if _vals(present, "max_pause_ms") else None,
        },
        "timing": {
            "speaking_duration_seconds": round(sum(_vals(present, "speaking_duration_seconds")), 2) if _vals(present, "speaking_duration_seconds") else None,
            "silence_duration_seconds": round(sum(_vals(present, "silence_duration_seconds")), 2) if _vals(present, "silence_duration_seconds") else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic dimension scores (starting points; AI may refine)
# ─────────────────────────────────────────────────────────────────────────────

def pace_score(avg_wpm: Optional[float]) -> Optional[float]:
    if avg_wpm is None:
        return None
    if PACE_TARGET_MIN <= avg_wpm <= PACE_TARGET_MAX:
        return 100.0
    if avg_wpm < PACE_TARGET_MIN:
        if avg_wpm <= PACE_FLOOR:
            return 20.0
        return round(20 + 80 * (avg_wpm - PACE_FLOOR) / (PACE_TARGET_MIN - PACE_FLOOR), 2)
    if avg_wpm >= PACE_CEIL:
        return 20.0
    return round(100 - 80 * (avg_wpm - PACE_TARGET_MAX) / (PACE_CEIL - PACE_TARGET_MAX), 2)


def confidence_score(filler_rate: float, hedge_rate: float) -> float:
    """Fewer fillers + less hedging → higher (observable) confidence signal."""
    return round(max(20.0, 100.0 - filler_rate * 3.0 - hedge_rate * 4.0), 2)


def conciseness_score(lang: dict) -> float:
    """Penalize repetition, filler, hedging and very long sentences."""
    penalty = 0.0
    penalty += lang["filler_rate"] * 2.0
    penalty += lang["hedge_rate"] * 2.5
    penalty += lang["repeated_phrase_count"] * 3.0
    penalty += max(0.0, lang["average_words_per_sentence"] - 22) * 2.0
    penalty += lang["repeated_word_ratio"] * 30.0
    return round(max(20.0, 100.0 - penalty), 2)


# ─────────────────────────────────────────────────────────────────────────────
# Per-segment + session-level aggregation
# ─────────────────────────────────────────────────────────────────────────────

def _segment_duration(seg) -> Optional[float]:
    """Speaking duration if the frontend supplied it, else segment duration."""
    am = getattr(seg, "audio_metrics", None) or {}
    spk = am.get("speaking_duration_seconds")
    if spk:
        try:
            return float(spk)
        except (TypeError, ValueError):
            pass
    return seg.duration_seconds or None


def segment_evidence(seg) -> dict:
    lang = language_stats(seg.transcript or "")
    dur = _segment_duration(seg)
    return {
        "segment_index": seg.segment_index,
        "start_seconds": seg.start_seconds,
        "end_seconds": seg.end_seconds,
        "transcript": seg.transcript or "",
        "word_count": seg.word_count or lang["total_words"],
        "wpm": wpm(seg.word_count or lang["total_words"], dur),
        "filler_count": lang["filler_count"],
        "hedge_count": lang["hedge_count"],
        "sentence_count": lang["sentence_count"],
        "audio_metrics": getattr(seg, "audio_metrics", None) or {},
    }


def session_evidence(segments: list) -> dict:
    """Full deterministic SESSION EVIDENCE PACKET (see requirement 5)."""
    ordered = sorted(segments, key=lambda s: s.segment_index)
    seg_ev = [segment_evidence(s) for s in ordered]
    full_text = " ".join((s.transcript or "") for s in ordered).strip()
    lang = language_stats(full_text)

    total_words = sum(e["word_count"] for e in seg_ev)
    total_duration = sum((s.duration_seconds or 0.0) for s in ordered)
    seg_wpms = [e["wpm"] for e in seg_ev if e["wpm"] is not None]

    avg_wpm = round(mean(seg_wpms), 2) if seg_wpms else wpm(total_words, total_duration)
    audio = aggregate_audio(ordered)
    speaking = audio["timing"]["speaking_duration_seconds"]
    silence = audio["timing"]["silence_duration_seconds"]
    speaking_ratio = None
    if speaking is not None and total_duration:
        speaking_ratio = round(min(1.0, speaking / total_duration), 3)

    packet = {
        "segment_count": len(ordered),
        "transcript": full_text,
        "segments": seg_ev,
        "timing": {
            "total_duration_seconds": round(total_duration, 2),
            "speaking_duration_seconds": speaking,
            "silence_duration_seconds": silence,
            "speaking_ratio": speaking_ratio,
        },
        "pace": {
            "total_word_count": total_words,
            "average_wpm": avg_wpm,
            "median_wpm": round(median(seg_wpms), 2) if seg_wpms else None,
            "minimum_segment_wpm": round(min(seg_wpms), 2) if seg_wpms else None,
            "maximum_segment_wpm": round(max(seg_wpms), 2) if seg_wpms else None,
            "wpm_standard_deviation": round(pstdev(seg_wpms), 2) if len(seg_wpms) > 1 else 0.0,
            "pace_variability": round(pstdev(seg_wpms) / mean(seg_wpms), 3) if len(seg_wpms) > 1 and mean(seg_wpms) else 0.0,
        },
        "pauses": audio["pauses"],
        "volume": audio["volume"],
        "pitch": audio["pitch"],
        "language": lang,
        "has_audio_metrics": audio["has_audio_metrics"],
    }

    # Deterministic starting scores.
    packet["deterministic_scores"] = {
        "pace": pace_score(avg_wpm),
        "confidence": confidence_score(lang["filler_rate"], lang["hedge_rate"]),
        "conciseness": conciseness_score(lang),
        "volume": audio["volume"]["consistency"],  # None without audio
    }
    packet["vocal_variety"] = vocal_variety(packet)
    return packet


# ─────────────────────────────────────────────────────────────────────────────
# Vocal variety diagnostic (not a weighted score)
# ─────────────────────────────────────────────────────────────────────────────

def vocal_variety(packet: dict) -> dict:
    pitch = packet.get("pitch", {})
    vol = packet.get("volume", {})
    pauses = packet.get("pauses", {})
    obs = []
    if pitch.get("std_dev_hz") is not None:
        obs.append(f"pitch varied by ~{pitch['std_dev_hz']} Hz within segments")
    if pitch.get("segment_variation_hz") is not None:
        obs.append(f"segment-to-segment pitch variation ~{pitch['segment_variation_hz']} Hz")
    if vol.get("rms_variability") is not None:
        obs.append("relative volume varied across the session")
    observation = "; ".join(obs) if obs else "No pitch/volume variability data supplied."
    return {
        "pitch_variability": pitch.get("std_dev_hz"),
        "volume_variability": vol.get("rms_variability"),
        "pause_variability": pauses.get("average_pause_ms"),
        "observation": observation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite score (weighted, null-aware, six dimensions)
# ─────────────────────────────────────────────────────────────────────────────

def clamp_score(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(max(0.0, min(100.0, float(value))), 2)


def composite_score(scores: dict) -> Optional[float]:
    """Weighted average over available dimensions (None dimensions excluded)."""
    num = denom = 0.0
    for dim in DIMENSIONS:
        val = scores.get(dim)
        if val is None:
            continue
        w = WEIGHTS.get(dim, 1.0)
        num += w * float(val)
        denom += w
    return round(num / denom, 2) if denom else None
