from sqlmodel import create_engine, Session, SQLModel
from app.models import User, Speech, SpeechMetrics
from app.services.scoring import top_speeches, average_metrics, find_mentors

engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)


def make_speech(session, user_id, overall):
    sp = Speech(user_id=user_id, status="done")
    session.add(sp); session.commit(); session.refresh(sp)
    m = SpeechMetrics(
        speech_id=sp.id,
        clarity=overall, volume=overall, pace=overall,
        confidence=overall, structure=overall, overall=overall,
    )
    session.add(m); session.commit()
    return sp


def test_top_speeches_returns_max_3():
    with Session(engine) as s:
        u = User(name="A"); s.add(u); s.commit(); s.refresh(u)
        for sc in [80, 75, 70, 65, 60]:
            make_speech(s, u.id, sc)
        result = top_speeches(u.id, s)
        assert len(result) <= 3


def test_top_speeches_fewer_than_3_no_crash():
    with Session(engine) as s:
        u = User(name="B"); s.add(u); s.commit(); s.refresh(u)
        make_speech(s, u.id, 70)
        result = top_speeches(u.id, s)
        assert len(result) == 1


def test_top_speeches_empty_no_crash():
    with Session(engine) as s:
        u = User(name="Empty"); s.add(u); s.commit(); s.refresh(u)
        result = top_speeches(u.id, s)
        assert result == []


def test_average_metrics_correct():
    with Session(engine) as s:
        u = User(name="C"); s.add(u); s.commit(); s.refresh(u)
        sp1 = make_speech(s, u.id, 80)
        sp2 = make_speech(s, u.id, 60)
        avg = average_metrics([sp1, sp2], s)
        assert avg["overall"] == 70


def test_average_metrics_empty_list():
    with Session(engine) as s:
        avg = average_metrics([], s)
        assert avg["overall"] == 0


def test_find_mentors_matches_weak_dimension():
    with Session(engine) as s:
        mentor = User(name="Mentor", is_mentor=True)
        learner = User(name="Learner")
        s.add(mentor); s.add(learner); s.commit()
        s.refresh(mentor); s.refresh(learner)
        make_speech(s, mentor.id, 90)    # mentor has high scores
        sp = make_speech(s, learner.id, 30)  # learner has low scores (all dims < 50)
        suggestions = find_mentors(sp.id, s)
        assert mentor.id in suggestions


def test_find_mentors_no_weak_dims_returns_empty():
    with Session(engine) as s:
        learner = User(name="Strong"); s.add(learner); s.commit(); s.refresh(learner)
        sp = make_speech(s, learner.id, 80)  # all scores >= 50, no weak dims
        suggestions = find_mentors(sp.id, s)
        assert suggestions == []
