from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.services.scoring import top_speeches, average_metrics

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile/{user_id}")
def get_profile(user_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    from app.models import User
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404)

    speeches = top_speeches(user_id, session)
    avg = average_metrics(speeches, session)

    return {
        "user": {
            "id": target.id,
            "name": target.name,
            "avatar_url": target.avatar_url,
            "career_tag": target.career_tag,
            "is_mentor": target.is_mentor,
        },
        "top_speeches": [{"id": s.id, "started_at": s.started_at} for s in speeches],
        "average_metrics": avg,
    }
