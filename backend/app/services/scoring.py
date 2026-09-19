"""Improvement-score logic that powers the leaderboard.

A user's `improvement_score` is a rolling blend of their recent presentation
scores plus a bonus for *trending upward* — we want to reward growth, not just
raw talent, so newcomers who keep improving can climb the board.
"""
from __future__ import annotations

from statistics import mean


def compute_improvement_score(recent_scores: list[float]) -> float:
    """Blend average recent performance with an upward-trend bonus.

    recent_scores: chronological list of a user's presentation scores (0-100).
    """
    if not recent_scores:
        return 0.0

    base = mean(recent_scores[-5:])  # recent form

    # Trend bonus: compare the first half vs second half of the window.
    trend_bonus = 0.0
    if len(recent_scores) >= 2:
        window = recent_scores[-6:]
        half = len(window) // 2
        early, late = mean(window[:half]), mean(window[half:])
        trend_bonus = max(0.0, (late - early)) * 0.5  # only reward improvement

    return round(min(100.0, base + trend_bonus), 2)
