from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import uuid4
from datetime import datetime


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    linkedin_id: Optional[str] = None
    name: str
    avatar_url: Optional[str] = None
    career_tag: Optional[str] = None
    is_mentor: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Speech(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    status: str = "live"
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: Optional[str] = None


class SpeechMetrics(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    speech_id: str = Field(foreign_key="speech.id")
    clarity: int = 0
    volume: int = 0
    pace: int = 0
    confidence: int = 0
    structure: int = 0
    overall: int = 0
    summary: str = ""
    suggestions: str = "[]"
    mentor_suggestions: str = "[]"


class RealtimeSegment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    speech_id: str = Field(foreign_key="speech.id")
    transcript: str
    nudge: str = ""
    segment_index: int
    recorded_at: str
    duration_seconds: float
    avg_volume: int = 0
    volume_variance: int = 0


class CommunityPost(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    speech_id: str = Field(foreign_key="speech.id")
    user_id: str = Field(foreign_key="user.id")
    is_public: bool = True
    career_tag: Optional[str] = None
    topic_tag: Optional[str] = None
    like_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Like(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    post_id: str = Field(foreign_key="communitypost.id")
    user_id: str = Field(foreign_key="user.id")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class MentorConnection(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    requester_id: str = Field(foreign_key="user.id")
    mentor_id: str = Field(foreign_key="user.id")
    speech_id: str = Field(foreign_key="speech.id")
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
