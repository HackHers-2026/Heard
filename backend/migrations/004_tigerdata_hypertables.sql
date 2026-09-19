-- Run this in the TigerData SQL editor (not Supabase).
-- Creates 3 hypertables for analytics: speech outcomes, segment stats, post engagement.

CREATE TABLE IF NOT EXISTS speech_events (
    time         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id      TEXT,
    speech_id    TEXT,
    overall      INT,
    clarity      INT,
    volume       INT,
    pace         INT,
    confidence   INT,
    structure    INT
) WITH (timescaledb.hypertable);

CREATE TABLE IF NOT EXISTS segment_events (
    time         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    speech_id    TEXT,
    pace_wpm     INT,
    avg_volume   INT
) WITH (timescaledb.hypertable);

CREATE TABLE IF NOT EXISTS post_likes (
    time         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    post_id      TEXT,
    user_id      TEXT,
    career_tag   TEXT
) WITH (timescaledb.hypertable);
