from statistics import mean, stdev
from sqlmodel import Session, select

from app.models import Speech, SpeechMetrics, User


def top_speeches(user_id: str, session: Session) -> list[Speech]:
    speeches = session.exec(
        select(Speech).where(Speech.user_id == user_id, Speech.status == "done")
    ).all()

    if not speeches:
        return []

    scored = []
    for sp in speeches:
        m = session.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)).first()
        if m:
            scored.append((sp, m.overall))

    scored.sort(key=lambda x: x[1], reverse=True)
    top5 = scored[:5]

    if len(top5) < 3:
        return [s for s, _ in top5]

    scores = [s for _, s in top5]
    avg = mean(scores)
    sd = stdev(scores) if len(scores) > 1 else 0
    filtered = [(sp, s) for sp, s in top5 if sd == 0 or abs(s - avg) / sd <= 1.5]
    return [sp for sp, _ in filtered[:3]]


def average_metrics(speeches: list[Speech], session: Session) -> dict:
    if not speeches:
        return {d: 0 for d in ["clarity", "volume", "pace", "confidence", "structure", "overall"]}

    metrics = []
    for sp in speeches:
        m = session.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == sp.id)).first()
        if m:
            metrics.append(m)

    if not metrics:
        return {d: 0 for d in ["clarity", "volume", "pace", "confidence", "structure", "overall"]}

    return {
        "clarity": int(mean(m.clarity for m in metrics)),
        "volume": int(mean(m.volume for m in metrics)),
        "pace": int(mean(m.pace for m in metrics)),
        "confidence": int(mean(m.confidence for m in metrics)),
        "structure": int(mean(m.structure for m in metrics)),
        "overall": int(mean(m.overall for m in metrics)),
    }


def find_mentors(speech_id: str, session: Session) -> list[str]:
    metrics = session.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == speech_id)).first()
    if not metrics:
        return []

    weak_dims = {
        "clarity": metrics.clarity,
        "volume": metrics.volume,
        "pace": metrics.pace,
        "confidence": metrics.confidence,
        "structure": metrics.structure,
    }
    weak = [dim for dim, score in weak_dims.items() if score < 50]
    if not weak:
        return []

    mentors = session.exec(select(User).where(User.is_mentor == True)).all()

    suggestions = set()
    for mentor in mentors:
        mentor_speeches = top_speeches(mentor.id, session)
        if not mentor_speeches:
            continue
        avg = average_metrics(mentor_speeches, session)
        if any(avg.get(dim, 0) >= 70 for dim in weak):
            suggestions.add(mentor.id)
        if len(suggestions) >= 3:
            break

    return list(suggestions)
