# Spec 05 — Gemini Integration

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file.  
**Requires:** Spec 04 routes exist (services are called from routes).  
**MCP:** Backboard MCP if available — makes session context stateful across nudge calls.

## services/gemini.py — 3 functions

### Stub fallback (no key)
```python
import os
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def _stub_mode():
    return not bool(GEMINI_KEY)
```
Every function checks `_stub_mode()` first and returns a hardcoded response.

---

### 1. encourage(mode, context)
```
Input:  mode = "quick" | "plan", context = optional user description
Output: { message: str, outline?: list[str] }

Prompt guidance:
- Tone: warm, peer-level, never patronising
- Quick mode: 1–2 sentences max, no questions
- Plan mode: pep talk + 3-point outline based on context
- Model: gemini-1.5-flash (free tier)

Stub: { message: "Your idea is worth sharing — the room needs to hear it." }
```

### 2. nudge(transcript, avg_volume, pace_wpm)
```
Input:  2-min transcript chunk + audio stats
Output: str ≤ 10 words  |  None if latency > 3s

Prompt guidance:
- Analyse pace (target: 120–150 wpm), volume consistency, filler words
- Return ONE short actionable nudge only
- Examples: "Slow down a little", "Speak up", "Great pace, keep going"
- If speech is good: positive reinforcement, not silence

Timeout: wrap call in asyncio.wait_for(..., timeout=3.0), return None on timeout

Stub: "You're doing great, keep going"
```

### 3. score(speech_id, session) — async, called as background task
```
Input:  all RealtimeSegments for speech_id (fetch from DB)
Output: saves SpeechMetrics row, marks Speech.status = "done"

Prompt guidance:
- Concatenate all segment transcripts in order
- Include avg_volume and volume_variance aggregates
- Score each dimension 0–100 (integers):
    clarity    — structure, coherence, vocabulary
    volume     — consistency from volume stats
    pace       — wpm vs 120–150 target range
    confidence — filler word density, hedging language
    structure  — detectable intro / body / conclusion
- overall = mean of 5 scores
- summary: 2–3 sentence honest but encouraging summary
- suggestions: list of 2–3 specific improvements

After saving metrics → call scoring.py:find_mentors(speech_id, session)

Stub: all scores = 70, summary = "Good effort.", suggestions = ["Vary your pace"]
```

## Backboard integration (if MCP available)
- Wrap nudge calls with Backboard session keyed on `speech_id`
- Lets Gemini remember earlier nudges in the same speech → avoids repeating the same feedback
- Only add after base Gemini calls work

## Tests (`tests/test_gemini.py`)

```python
import pytest, os
os.environ.pop("GEMINI_API_KEY", None)   # force stub mode for all tests
from app.services.gemini import encourage, nudge, score

def test_encourage_quick_stub():
    result = encourage("quick", None)
    assert "message" in result
    assert isinstance(result["message"], str)
    assert "outline" not in result

def test_encourage_plan_stub_has_outline():
    result = encourage("plan", "pitch to investors")
    assert "outline" in result
    assert isinstance(result["outline"], list)

def test_nudge_returns_short_string_or_none():
    result = nudge("hello world um yeah so basically", avg_volume=60, pace_wpm=90)
    assert result is None or (isinstance(result, str) and len(result.split()) <= 10)

def test_nudge_stub_never_raises():
    # Should not raise even with empty transcript
    result = nudge("", avg_volume=0, pace_wpm=0)
    assert result is None or isinstance(result, str)

@pytest.mark.asyncio
async def test_score_stub_saves_metrics(tmp_db_session):
    # tmp_db_session is a pytest fixture providing an in-memory session
    # with a seeded Speech + RealtimeSegments
    await score(tmp_db_session["speech_id"], tmp_db_session["session"])
    metrics = tmp_db_session["get_metrics"]()
    assert metrics is not None
    assert 0 <= metrics.overall <= 100
    assert metrics.summary != ""
```

## Done when
All tests pass: `pytest tests/test_gemini.py`
