"""Pydantic request/response schemas (API contracts shared by both frontends)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import Domain, FeedbackKind


# ---- Auth ----
class UserCreate(BaseModel):
    email: str
    display_name: str
    password: str
    domain: Domain = Domain.tech
    is_mentor: bool = False


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    email: str
    display_name: str
    domain: Domain
    is_mentor: bool
    improvement_score: float


# ---- Practice sessions ----
class SessionCreate(BaseModel):
    domain: Domain
    title: str = "Untitled practice"
    slides_url: Optional[str] = None


class SessionPublic(BaseModel):
    id: int
    domain: Domain
    title: str
    slides_url: Optional[str]
    score: Optional[float]
    created_at: datetime


# ---- Transcription / live feedback (used by the extension) ----
class TranscribeRequest(BaseModel):
    """A chunk of audio has already been transcribed client-side OR
    the extension forwards raw text. Send the transcript chunk here."""
    session_id: int
    text: str
    duration_seconds: Optional[float] = None


class LiveFeedbackResponse(BaseModel):
    """What the extension renders as a pop-up over Google Slides."""
    session_id: int
    trigger_text: str
    feedback: str
    tip_category: str  # e.g. "pacing", "filler-words", "confidence", "clarity"


# ---- Post-practice summary (used by the web app chat view) ----
class SummaryResponse(BaseModel):
    session_id: int
    summary: str
    score: float
    strengths: list[str]
    improvements: list[str]


class FeedbackPublic(BaseModel):
    id: int
    kind: FeedbackKind
    trigger_text: Optional[str]
    content: str
    score: Optional[float]
    created_at: datetime


# ---- Leaderboard ----
class LeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    domain: Domain
    improvement_score: float
    is_mentor: bool
    rank: int


# ---- DMs ----
class MessageCreate(BaseModel):
    recipient_id: int
    body: str


class MessagePublic(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    body: str
    read: bool
    created_at: datetime


# ---- Pre-training ----
class PreTrainingResponse(BaseModel):
    domain: Domain
    coaching: str
    checklist: list[str]
