from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models import MentorConnection

router = APIRouter(prefix="/api", tags=["mentor"])


class MentorConnectRequest(BaseModel):
    mentor_id: str
    speech_id: str


@router.post("/mentor/connect")
def mentor_connect(
    body: MentorConnectRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conn = MentorConnection(
        requester_id=user.id,
        mentor_id=body.mentor_id,
        speech_id=body.speech_id,
    )
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return {
        "connection": {
            "id": conn.id,
            "mentor_id": conn.mentor_id,
            "requester_id": conn.requester_id,
            "speech_id": conn.speech_id,
            "status": conn.status,
        }
    }
