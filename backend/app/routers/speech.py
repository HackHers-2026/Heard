import json
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.database import engine as db_engine
from app.dependencies import get_current_user
from app.models import Speech, RealtimeSegment, SpeechMetrics
from app.services import gemini
from app.services import tigertable

router = APIRouter(prefix="/api/speech", tags=["speech"])


@router.post("/start")
def speech_start(user=Depends(get_current_user), session: Session = Depends(get_session)):
    speech = Speech(user_id=user.id)
    session.add(speech)
    session.commit()
    session.refresh(speech)
    return {"speech_id": speech.id, "session_token": speech.id}


class SegmentRequest(BaseModel):
    speech_id: str
    transcript: str
    segment_index: int
    recorded_at: str
    duration_seconds: float
    avg_volume: int = 0
    volume_variance: int = 0


@router.post("/segment")
def speech_segment(body: SegmentRequest, session: Session = Depends(get_session)):
    pace_wpm = 0
    if body.duration_seconds > 0:
        pace_wpm = int(len(body.transcript.split()) / (body.duration_seconds / 60))

    nudge = gemini.nudge(body.transcript, avg_volume=body.avg_volume, pace_wpm=pace_wpm)

    seg = RealtimeSegment(
        speech_id=body.speech_id,
        transcript=body.transcript,
        segment_index=body.segment_index,
        recorded_at=body.recorded_at,
        duration_seconds=body.duration_seconds,
        avg_volume=body.avg_volume,
        volume_variance=body.volume_variance,
        nudge=nudge or "",
    )
    session.add(seg)
    session.commit()

    tigertable.track("segment.posted", {
        "speech_id": body.speech_id,
        "pace_wpm": pace_wpm,
        "avg_volume": body.avg_volume,
    })

    return {"nudge": nudge}


class EndRequest(BaseModel):
    speech_id: str


def _score_background(speech_id: str):
    with Session(db_engine) as s:
        gemini.score(speech_id, s)


@router.post("/end")
def speech_end(body: EndRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    speech = session.get(Speech, body.speech_id)
    if speech:
        speech.ended_at = datetime.utcnow().isoformat()
        session.add(speech)
        session.commit()
    background_tasks.add_task(_score_background, body.speech_id)
    return {"report_ready": False}


@router.get("/{speech_id}/report")
def speech_report(speech_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    speech = session.get(Speech, speech_id)
    if not speech or speech.status != "done":
        raise HTTPException(status_code=404, detail="Report not ready")
    metrics = session.exec(select(SpeechMetrics).where(SpeechMetrics.speech_id == speech_id)).first()
    if not metrics:
        raise HTTPException(status_code=404, detail="Metrics not found")
    return {
        "speech": {
            "id": speech.id,
            "status": speech.status,
            "started_at": speech.started_at,
            "ended_at": speech.ended_at,
        },
        "metrics": {
            "clarity": metrics.clarity,
            "volume": metrics.volume,
            "pace": metrics.pace,
            "confidence": metrics.confidence,
            "structure": metrics.structure,
            "overall": metrics.overall,
            "summary": metrics.summary,
            "suggestions": json.loads(metrics.suggestions),
        },
    }
