"""Per-domain leaderboard + mentor recommendations.

Women who have improved the most rise to the top and are surfaced as mentors to
those still building confidence in the same domain.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.security import get_current_user
from app.database import get_session
from app.models import Domain, User
from app.schemas import LeaderboardEntry, UserPublic

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/{domain}", response_model=list[LeaderboardEntry])
def leaderboard(domain: Domain, session: Session = Depends(get_session)):
    users = session.exec(
        select(User)
        .where(User.domain == domain)
        .order_by(User.improvement_score.desc())
    ).all()
    return [
        LeaderboardEntry(
            user_id=u.id,
            display_name=u.display_name,
            domain=u.domain,
            improvement_score=u.improvement_score,
            is_mentor=u.is_mentor,
            rank=i + 1,
        )
        for i, u in enumerate(users)
    ]


@router.get("/{domain}/mentors", response_model=list[UserPublic])
def recommended_mentors(
    domain: Domain,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Top performers in the current user's domain, recommended as mentors."""
    users = session.exec(
        select(User)
        .where(User.domain == domain)
        .where(User.id != current.id)
        .order_by(User.improvement_score.desc())
        .limit(5)
    ).all()
    return users
