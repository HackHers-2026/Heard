"""
Seed realistic mock data into the DB (local SQLite or Supabase via DATABASE_URL).
Run: python seed.py
Idempotent — skips rows that already exist by ID.
"""
import json
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select
from app.database import engine, init_db
from app.models import (
    User, Speech, SpeechMetrics, RealtimeSegment,
    CommunityPost, Like, MentorConnection, ChatMessage
)
from app.services.gemini import make_session_hash

init_db()

USERS = [
    dict(id="seed-user-1", name="Priya Sharma",    career_tag="engineering", is_mentor=False, avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=priya"),
    dict(id="seed-user-2", name="Mei Lin",         career_tag="engineering", is_mentor=True,  avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=mei"),
    dict(id="seed-user-3", name="Aisha Okonkwo",   career_tag="finance",     is_mentor=True,  avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=aisha"),
    dict(id="seed-user-4", name="Sofia Reyes",     career_tag="marketing",   is_mentor=False, avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=sofia"),
    dict(id="seed-user-5", name="Rachel Kim",      career_tag="law",         is_mentor=True,  avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=rachel"),
    dict(id="seed-user-6", name="Nadia Torres",    career_tag="engineering", is_mentor=False, avatar_url="https://api.dicebear.com/7.x/avataaars/svg?seed=nadia"),
]

SPEECHES = [
    dict(id="seed-speech-1", user_id="seed-user-1", status="done",
         started_at="2026-09-10T10:00:00", ended_at="2026-09-10T10:22:00"),
    dict(id="seed-speech-2", user_id="seed-user-1", status="done",
         started_at="2026-09-14T14:00:00", ended_at="2026-09-14T14:18:00"),
    dict(id="seed-speech-3", user_id="seed-user-2", status="done",
         started_at="2026-09-12T09:00:00", ended_at="2026-09-12T09:25:00"),
    dict(id="seed-speech-4", user_id="seed-user-3", status="done",
         started_at="2026-09-15T11:00:00", ended_at="2026-09-15T11:20:00"),
    dict(id="seed-speech-5", user_id="seed-user-4", status="done",
         started_at="2026-09-16T15:00:00", ended_at="2026-09-16T15:15:00"),
    dict(id="seed-speech-6", user_id="seed-user-6", status="done",
         started_at="2026-09-17T10:00:00", ended_at="2026-09-17T10:20:00"),
]

METRICS = [
    dict(speech_id="seed-speech-1", clarity=72, volume=68, pace=75, confidence=65, structure=70, overall=70,
         summary="Good structure overall. Filler words were noticeable — try pausing instead of using 'um'.",
         suggestions=json.dumps(["Reduce filler words", "Slow down in the opening", "End with a stronger call to action"])),
    dict(speech_id="seed-speech-2", clarity=80, volume=74, pace=82, confidence=76, structure=78, overall=78,
         summary="Solid improvement from last session. Pace and clarity were strong. Work on volume consistency.",
         suggestions=json.dumps(["Project your voice more in the first minute", "Add a concrete data point to support your main claim"])),
    dict(speech_id="seed-speech-3", clarity=91, volume=88, pace=90, confidence=89, structure=92, overall=90,
         summary="Excellent delivery. Clear structure, confident tone, and well-paced throughout.",
         suggestions=json.dumps(["Consider adding a personal story to connect with the audience", "The conclusion could be more memorable"])),
    dict(speech_id="seed-speech-4", clarity=85, volume=82, pace=78, confidence=84, structure=86, overall=83,
         summary="Strong and authoritative. Financial data was presented clearly. Opening was especially effective.",
         suggestions=json.dumps(["Vary your pace more in the middle section", "Anticipate the 'why now' question"])),
    dict(speech_id="seed-speech-5", clarity=70, volume=65, pace=72, confidence=68, structure=69, overall=69,
         summary="Creative framing and good energy. Structure needs more work — the body section felt scattered.",
         suggestions=json.dumps(["Add clearer transitions between points", "Lead with the customer story earlier"])),
    dict(speech_id="seed-speech-6", clarity=74, volume=71, pace=70, confidence=66, structure=73, overall=71,
         summary="Consistent volume and clear vocabulary. Confidence language needs work — too many hedges.",
         suggestions=json.dumps(["Replace 'kind of' and 'sort of' with direct statements", "Practice the opening 30 seconds until fluent"])),
]

SEGMENTS = [
    dict(speech_id="seed-speech-1", segment_index=0, transcript="Hello everyone, um, I'd like to talk about our product roadmap. So basically we have three main initiatives this quarter.", recorded_at="2026-09-10T10:00:00", duration_seconds=120, avg_volume=65, volume_variance=8),
    dict(speech_id="seed-speech-1", segment_index=1, transcript="The first initiative focuses on user retention. We kind of need to improve our onboarding flow and make sure users get value quickly.", recorded_at="2026-09-10T10:02:00", duration_seconds=120, avg_volume=68, volume_variance=6),
    dict(speech_id="seed-speech-2", segment_index=0, transcript="Good morning. Today I want to walk you through our Q3 results and what they mean for Q4 planning. We exceeded our revenue target by 12%.", recorded_at="2026-09-14T14:00:00", duration_seconds=120, avg_volume=72, volume_variance=5),
    dict(speech_id="seed-speech-3", segment_index=0, transcript="The data shows a clear pattern: companies that invest in employee development see 34% higher retention. Let me show you exactly how this applies to our situation.", recorded_at="2026-09-12T09:00:00", duration_seconds=120, avg_volume=85, volume_variance=4),
]

POSTS = [
    dict(id="seed-post-1", speech_id="seed-speech-2", user_id="seed-user-1", career_tag="engineering", topic_tag="leadership", like_count=7, created_at="2026-09-14T15:00:00"),
    dict(id="seed-post-2", speech_id="seed-speech-3", user_id="seed-user-2", career_tag="engineering", topic_tag="data",       like_count=14, created_at="2026-09-12T10:00:00"),
    dict(id="seed-post-3", speech_id="seed-speech-4", user_id="seed-user-3", career_tag="finance",     topic_tag="strategy",   like_count=9,  created_at="2026-09-15T12:00:00"),
    dict(id="seed-post-4", speech_id="seed-speech-5", user_id="seed-user-4", career_tag="marketing",   topic_tag="branding",   like_count=5,  created_at="2026-09-16T16:00:00"),
]

CHAT = [
    dict(speech_id="seed-speech-1", role="user",  phase="preptalk", content="I'm really nervous about this presentation. It's my first time presenting to the whole company.", summary="nervous about presentation"),
    dict(speech_id="seed-speech-1", role="model", phase="preptalk", content="That nervous energy is actually a good sign — it means you care. Channel it into enthusiasm. Your roadmap work is solid; you just need to trust it. Start with one confident sentence about the impact of what you're sharing.", summary="nervous energy is good"),
    dict(speech_id="seed-speech-1", role="user",  phase="talksummary", content="How do I reduce my filler words?", summary="asked about filler words"),
    dict(speech_id="seed-speech-1", role="model", phase="talksummary", content="Try the pause technique: when you feel an 'um' coming, pause for 1-2 seconds instead. It sounds more authoritative than filling the silence. Practice by recording yourself for 2 minutes and counting fillers — awareness alone reduces them by 30%.", summary="pause instead of filler"),
]


def seed():
    with Session(engine) as s:
        # Users
        for u in USERS:
            if not s.get(User, u["id"]):
                s.add(User(**u))
        s.commit()
        print(f"✓ {len(USERS)} users")

        # Speeches
        for sp in SPEECHES:
            if not s.get(Speech, sp["id"]):
                s.add(Speech(**sp))
        s.commit()
        print(f"✓ {len(SPEECHES)} speeches")

        # Segments
        for seg in SEGMENTS:
            existing = s.exec(
                select(RealtimeSegment)
                .where(RealtimeSegment.speech_id == seg["speech_id"])
                .where(RealtimeSegment.segment_index == seg["segment_index"])
            ).first()
            if not existing:
                s.add(RealtimeSegment(**seg))
        s.commit()
        print(f"✓ {len(SEGMENTS)} segments")

        # Metrics
        for m in METRICS:
            existing = s.exec(
                select(SpeechMetrics).where(SpeechMetrics.speech_id == m["speech_id"])
            ).first()
            if not existing:
                s.add(SpeechMetrics(**m))
        s.commit()
        print(f"✓ {len(METRICS)} metrics")

        # Posts
        for p in POSTS:
            if not s.get(CommunityPost, p["id"]):
                s.add(CommunityPost(**p))
        s.commit()
        print(f"✓ {len(POSTS)} posts")

        # Chat messages
        for c in CHAT:
            session_hash = make_session_hash(c["speech_id"])
            existing = s.exec(
                select(ChatMessage)
                .where(ChatMessage.session_hash == session_hash)
                .where(ChatMessage.role == c["role"])
                .where(ChatMessage.phase == c["phase"])
                .where(ChatMessage.content == c["content"])
            ).first()
            if not existing:
                s.add(ChatMessage(
                    session_hash=session_hash,
                    speech_id=c["speech_id"],
                    role=c["role"],
                    phase=c["phase"],
                    content=c["content"],
                    summary=c["summary"],
                ))
        s.commit()
        print(f"✓ {len(CHAT)} chat messages")

    print("\nDone. Seed data is live.")


if __name__ == "__main__":
    seed()
