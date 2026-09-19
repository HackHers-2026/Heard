"""Database models for Heard.

Core domain:
  User        -> a woman practicing her pitch / a mentor
  Session     -> one practice run (tied to a domain + optional Google Slides)
  Transcript  -> the transcribed speech for a Session (from ElevenLabs)
  Feedback    -> AI feedback items (live pop-ups + final summary/score) from Gemini
  Message     -> DM between a struggling user and a mentor on the leaderboard
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Domain(str, Enum):
    tech = "tech"
    law = "law"
    finance = "finance"
    marketing = "marketing"


class FeedbackKind(str, Enum):
    live = "live"          # real-time pop-up shown in the extension
    summary = "summary"    # post-practice summary shown in the web app


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    display_name: str
    hashed_password: str
    domain: Domain = Domain.tech
    is_mentor: bool = False
    # Rolling improvement score (0-100) used to rank the leaderboard.
    improvement_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PracticeSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    domain: Domain
    title: str = "Untitled practice"
    slides_url: Optional[str] = None
    # Overall Gemini-assigned presentation score for this run (0-100).
    score: Optional[float] = None
    # Backboard memory thread id so Gemini keeps context across runs.
    backboard_thread_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Transcript(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="practicesession.id", index=True)
    text: str
    words: Optional[int] = None
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="practicesession.id", index=True)
    kind: FeedbackKind = FeedbackKind.live
    # For live feedback, the transcript chunk that triggered it.
    trigger_text: Optional[str] = None
    content: str
    # Optional numeric sub-score attached to a summary (0-100).
    score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sender_id: int = Field(foreign_key="user.id", index=True)
    recipient_id: int = Field(foreign_key="user.id", index=True)
    body: str
    read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
