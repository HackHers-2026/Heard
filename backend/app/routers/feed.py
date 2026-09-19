from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional

from app.database import get_session
from app.dependencies import get_current_user
from app.models import CommunityPost, Like

router = APIRouter(prefix="/api", tags=["feed"])


class FeedPostRequest(BaseModel):
    speech_id: str
    career_tag: Optional[str] = None
    topic_tag: Optional[str] = None


@router.get("/feed")
def get_feed(
    career_tag: Optional[str] = Query(None),
    topic_tag: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20),
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    query = select(CommunityPost).where(CommunityPost.is_public == True)
    if career_tag:
        query = query.where(CommunityPost.career_tag == career_tag)
    if topic_tag:
        query = query.where(CommunityPost.topic_tag == topic_tag)
    query = query.order_by(CommunityPost.created_at.desc()).limit(limit)

    posts = session.exec(query).all()
    return {
        "posts": [
            {
                "id": p.id,
                "speech_id": p.speech_id,
                "user_id": p.user_id,
                "career_tag": p.career_tag,
                "topic_tag": p.topic_tag,
                "like_count": p.like_count,
                "created_at": p.created_at,
            }
            for p in posts
        ],
        "next_cursor": None,
    }


@router.post("/feed")
def create_feed_post(
    body: FeedPostRequest,
    user=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    post = CommunityPost(
        speech_id=body.speech_id,
        user_id=user.id,
        career_tag=body.career_tag,
        topic_tag=body.topic_tag,
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return {"id": post.id, "speech_id": post.speech_id, "user_id": post.user_id}


@router.post("/feed/{post_id}/like")
def toggle_like(post_id: str, user=Depends(get_current_user), session: Session = Depends(get_session)):
    post = session.get(CommunityPost, post_id)
    if not post:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    existing = session.exec(
        select(Like).where(Like.post_id == post_id, Like.user_id == user.id)
    ).first()

    if existing:
        session.delete(existing)
        post.like_count = max(0, post.like_count - 1)
        liked = False
    else:
        session.add(Like(post_id=post_id, user_id=user.id))
        post.like_count += 1
        liked = True

    session.add(post)
    session.commit()
    return {"liked": liked, "like_count": post.like_count}
