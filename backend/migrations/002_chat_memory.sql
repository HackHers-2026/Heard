-- Chat memory: stores conversation history per session, identified by a short hash.
-- session_hash is derived by the backend (sha256 of speech_id, truncated to 16 chars).
-- role: 'user' | 'model'

CREATE TABLE IF NOT EXISTS chatmessage (
    id          TEXT PRIMARY KEY,
    session_hash TEXT NOT NULL,
    speech_id   TEXT REFERENCES speech(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'model')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_chatmessage_session_hash ON chatmessage (session_hash);
