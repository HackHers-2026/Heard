# Spec 06 — Scoring & Mentor Matching

**Context:** `CLAUDE.md` + `docs/contracts.md` + this file.  
**Requires:** Spec 05 done (score() calls find_mentors).

## services/scoring.py — 3 functions

### 1. top_speeches(user_id, session) → list[Speech]
```
- Fetch all Speech where user_id = user_id and status = "done"
- Join SpeechMetrics, sort by overall DESC
- Take top 5, drop outliers (z-score > 1.5 on overall)
- Return top 3 remaining
- If < 3 speeches total: return all (no outlier drop)
```

### 2. average_metrics(speeches, session) → dict
```
- Fetch SpeechMetrics for each speech
- Average each of the 5 dimensions + overall across all
- Return:
  {
    clarity: int, volume: int, pace: int,
    confidence: int, structure: int, overall: int
  }
```

### 3. find_mentors(speech_id, session) → list[str]
Called by gemini.py:score() after metrics are saved.
```
- Fetch SpeechMetrics for this speech
- Find weak dimensions: score < 50
- Query Users where is_mentor = True
- For each weak dimension, find users whose average on that dimension ≥ 70
  (use top_speeches + average_metrics to get their averages)
- Deduplicate, return up to 3 user IDs
- Save as SpeechMetrics.mentor_suggestions (JSON array)
```

## Tests (`tests/test_scoring.py`)

```python
from sqlmodel import create_engine, Session, SQLModel
from app.models import User, Speech, SpeechMetrics
from app.services.scoring import top_speeches, average_metrics, find_mentors

engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)

def make_speech(session, user_id, overall):
    sp = Speech(user_id=user_id, status="done")
    session.add(sp); session.commit(); session.refresh(sp)
    m = SpeechMetrics(speech_id=sp.id, clarity=overall, volume=overall,
                      pace=overall, confidence=overall, structure=overall, overall=overall)
    session.add(m); session.commit()
    return sp

def test_top_speeches_returns_max_3():
    with Session(engine) as s:
        u = User(name="A"); s.add(u); s.commit(); s.refresh(u)
        for score in [80, 75, 70, 65, 60]:
            make_speech(s, u.id, score)
        result = top_speeches(u.id, s)
        assert len(result) <= 3

def test_top_speeches_fewer_than_3_no_crash():
    with Session(engine) as s:
        u = User(name="B"); s.add(u); s.commit(); s.refresh(u)
        make_speech(s, u.id, 70)
        result = top_speeches(u.id, s)
        assert len(result) == 1

def test_average_metrics_correct():
    with Session(engine) as s:
        u = User(name="C"); s.add(u); s.commit(); s.refresh(u)
        sp1 = make_speech(s, u.id, 80)
        sp2 = make_speech(s, u.id, 60)
        avg = average_metrics([sp1, sp2], s)
        assert avg["overall"] == 70

def test_find_mentors_matches_weak_dimension():
    with Session(engine) as s:
        mentor = User(name="Mentor", is_mentor=True)
        learner = User(name="Learner")
        s.add(mentor); s.add(learner); s.commit()
        s.refresh(mentor); s.refresh(learner)
        # Mentor has high clarity score
        make_speech(s, mentor.id, 90)
        # Learner has low clarity score
        sp = make_speech(s, learner.id, 30)
        suggestions = find_mentors(sp.id, s)
        assert mentor.id in suggestions
```

## Done when
All tests pass: `pytest tests/test_scoring.py`
