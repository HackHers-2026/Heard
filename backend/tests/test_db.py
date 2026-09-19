from sqlmodel import create_engine, Session, SQLModel, inspect
from app.models import User, Speech, SpeechMetrics, RealtimeSegment, CommunityPost, Like, MentorConnection

engine = create_engine("sqlite:///:memory:")


def setup_module():
    SQLModel.metadata.create_all(engine)


def test_all_tables_exist():
    tables = inspect(engine).get_table_names()
    for t in ["user", "speech", "speechmetrics", "realtimesegment", "communitypost", "like", "mentorconnection"]:
        assert t in tables


def test_user_create():
    with Session(engine) as s:
        u = User(name="Test", linkedin_id="li_123")
        s.add(u)
        s.commit()
        s.refresh(u)
        assert u.id is not None
        assert u.is_mentor == False


def test_speech_create():
    with Session(engine) as s:
        u = User(name="A")
        s.add(u)
        s.commit()
        s.refresh(u)
        sp = Speech(user_id=u.id)
        s.add(sp)
        s.commit()
        s.refresh(sp)
        assert sp.status == "live"
        assert sp.ended_at is None


def test_realtime_segment_audio_fields():
    with Session(engine) as s:
        u = User(name="B")
        s.add(u)
        s.commit()
        s.refresh(u)
        sp = Speech(user_id=u.id)
        s.add(sp)
        s.commit()
        s.refresh(sp)
        seg = RealtimeSegment(
            speech_id=sp.id,
            transcript="hello",
            segment_index=0,
            recorded_at="2026-01-01T00:00:00",
            duration_seconds=120.0,
            avg_volume=65,
            volume_variance=10,
        )
        s.add(seg)
        s.commit()
        s.refresh(seg)
        assert seg.avg_volume == 65
