-- Heard v2 schema: profiles, channels, threads, training sessions, DMs.
-- Run via Supabase SQL editor or MCP apply_migration.
--
-- Conventions mirror 001_initial_schema.sql: text ids (== Supabase auth.uid()::text
-- for profiles), text ISO timestamps, jsonb for structured columns. Idempotent.
--
-- NOTE: the FastAPI backend also enforces ownership in code and may use the
-- service-role key (which bypasses RLS). RLS below is defense-in-depth for any
-- client that talks to Supabase directly (e.g. Realtime).

create extension if not exists "pgcrypto";

-- ─────────────────────────────────────────────────────────────────────────────
-- profiles  (id == auth.users.id as text)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists profiles (
  id           text primary key,
  display_name text,
  username     text unique,
  avatar_url   text,
  bio          text,
  is_private   boolean not null default false,
  created_at   text not null default now()::text,
  updated_at   text not null default now()::text
);

-- ─────────────────────────────────────────────────────────────────────────────
-- channels + memberships
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists channels (
  id          text primary key default gen_random_uuid()::text,
  slug        text not null unique,
  name        text not null,
  description text not null default '',
  created_at  text not null default now()::text
);

create table if not exists user_channel_memberships (
  id         text primary key default gen_random_uuid()::text,
  user_id    text not null references profiles(id) on delete cascade,
  channel_id text not null references channels(id) on delete cascade,
  joined_at  text not null default now()::text,
  unique (user_id, channel_id)
);
create index if not exists ix_membership_user on user_channel_memberships(user_id);
create index if not exists ix_membership_channel on user_channel_memberships(channel_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- training sessions + transcript segments + feedback
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists training_sessions (
  id               text primary key default gen_random_uuid()::text,
  user_id          text not null references profiles(id) on delete cascade,
  channel_id       text not null references channels(id) on delete cascade,
  title            text not null default '',
  status           text not null default 'ACTIVE',   -- ACTIVE|PROCESSING|COMPLETED|FAILED
  started_at       text not null default now()::text,
  ended_at         text,
  duration_seconds real not null default 0,
  total_words      integer not null default 0,
  created_at       text not null default now()::text
);
create index if not exists ix_session_user_channel_created
  on training_sessions(user_id, channel_id, created_at);
create index if not exists ix_session_channel_status
  on training_sessions(channel_id, status);

create table if not exists transcript_segments (
  id               text primary key default gen_random_uuid()::text,
  session_id       text not null references training_sessions(id) on delete cascade,
  segment_index    integer not null,
  transcript       text not null default '',
  start_seconds    real not null default 0,
  end_seconds      real not null default 0,
  duration_seconds real not null default 0,
  word_count       integer not null default 0,
  audio_metrics    jsonb not null default '{}'::jsonb,
  created_at       text not null default now()::text,
  unique (session_id, segment_index)
);
create index if not exists ix_segment_session on transcript_segments(session_id, segment_index);

create table if not exists session_feedback (
  id                 text primary key default gen_random_uuid()::text,
  session_id         text not null unique references training_sessions(id) on delete cascade,
  clarity_score      real,
  volume_score       real,          -- NULL when no audio metrics supplied
  pace_score         real,
  confidence_score   real,
  structure_score    real,
  overall_score      real,
  filler_count       integer not null default 0,
  filler_rate        real not null default 0,
  average_wpm        real not null default 0,
  volume_consistency real,
  strengths          jsonb not null default '[]'::jsonb,
  improvements       jsonb not null default '[]'::jsonb,
  summary            text not null default '',
  detailed_feedback  jsonb not null default '{}'::jsonb,
  created_at         text not null default now()::text
);

-- ─────────────────────────────────────────────────────────────────────────────
-- chat threads + messages  (PRE_TRAINING | POST_TRAINING)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists chat_threads (
  id                  text primary key default gen_random_uuid()::text,
  user_id             text not null references profiles(id) on delete cascade,
  channel_id          text not null references channels(id) on delete cascade,
  thread_type         text not null default 'PRE_TRAINING',
  session_id          text references training_sessions(id) on delete cascade,
  title               text not null default '',
  backboard_thread_id text,
  created_at          text not null default now()::text,
  updated_at          text not null default now()::text
);
create index if not exists ix_thread_user_channel_updated
  on chat_threads(user_id, channel_id, updated_at);
create index if not exists ix_thread_session on chat_threads(session_id);

create table if not exists chat_messages (
  id          text primary key default gen_random_uuid()::text,
  thread_id   text not null references chat_threads(id) on delete cascade,
  sender_type text not null,   -- user|assistant|system|transcript
  content     text not null,
  metadata    jsonb not null default '{}'::jsonb,
  created_at  text not null default now()::text
);
create index if not exists ix_message_thread_created on chat_messages(thread_id, created_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- direct messages
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists dm_conversations (
  id         text primary key default gen_random_uuid()::text,
  pair_key   text unique,        -- "min(uid)|max(uid)" — prevents duplicate 1:1s
  created_at text not null default now()::text,
  updated_at text not null default now()::text
);

create table if not exists dm_members (
  id              text primary key default gen_random_uuid()::text,
  conversation_id text not null references dm_conversations(id) on delete cascade,
  user_id         text not null references profiles(id) on delete cascade,
  unique (conversation_id, user_id)
);
create index if not exists ix_dm_member_user on dm_members(user_id);

create table if not exists dm_messages (
  id              text primary key default gen_random_uuid()::text,
  conversation_id text not null references dm_conversations(id) on delete cascade,
  sender_id       text not null references profiles(id) on delete cascade,
  content         text not null,
  created_at      text not null default now()::text,
  read_at         text
);
create index if not exists ix_dm_message_conv_created on dm_messages(conversation_id, created_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed channels (idempotent)
-- ─────────────────────────────────────────────────────────────────────────────
insert into channels (slug, name, description) values
  ('technology', 'Technology', 'Practice technical talks, demos and architecture reviews.'),
  ('finance',    'Finance',    'Pitch numbers, strategy and financial narratives with clarity.'),
  ('law',        'Law',        'Sharpen argument structure and precise, persuasive delivery.'),
  ('marketing',  'Marketing',  'Tell brand and product stories that land.'),
  ('healthcare', 'Healthcare', 'Communicate complex care and research clearly.'),
  ('education',  'Education',   'Explain, teach and present with confidence.'),
  ('general',    'General',     'Everyday speaking practice across any topic.')
on conflict (slug) do nothing;

-- ─────────────────────────────────────────────────────────────────────────────
-- Row Level Security
-- auth.uid() returns uuid; compare against text ids via ::text.
-- ─────────────────────────────────────────────────────────────────────────────
alter table profiles                 enable row level security;
alter table channels                 enable row level security;
alter table user_channel_memberships enable row level security;
alter table training_sessions        enable row level security;
alter table transcript_segments      enable row level security;
alter table session_feedback         enable row level security;
alter table chat_threads             enable row level security;
alter table chat_messages            enable row level security;
alter table dm_conversations         enable row level security;
alter table dm_members               enable row level security;
alter table dm_messages              enable row level security;

-- profiles: anyone authenticated may read public identity; you edit only your own.
drop policy if exists profiles_read on profiles;
create policy profiles_read on profiles for select to authenticated using (true);
drop policy if exists profiles_update on profiles;
create policy profiles_update on profiles for update to authenticated
  using (auth.uid()::text = id) with check (auth.uid()::text = id);
drop policy if exists profiles_insert on profiles;
create policy profiles_insert on profiles for insert to authenticated
  with check (auth.uid()::text = id);

-- channels: readable by all authenticated users.
drop policy if exists channels_read on channels;
create policy channels_read on channels for select to authenticated using (true);

-- memberships: you manage only your own rows.
drop policy if exists membership_rw on user_channel_memberships;
create policy membership_rw on user_channel_memberships for all to authenticated
  using (auth.uid()::text = user_id) with check (auth.uid()::text = user_id);

-- training data: owner-only.
drop policy if exists sessions_rw on training_sessions;
create policy sessions_rw on training_sessions for all to authenticated
  using (auth.uid()::text = user_id) with check (auth.uid()::text = user_id);

drop policy if exists segments_rw on transcript_segments;
create policy segments_rw on transcript_segments for all to authenticated
  using (exists (select 1 from training_sessions s
                 where s.id = transcript_segments.session_id
                   and s.user_id = auth.uid()::text))
  with check (exists (select 1 from training_sessions s
                      where s.id = transcript_segments.session_id
                        and s.user_id = auth.uid()::text));

drop policy if exists feedback_rw on session_feedback;
create policy feedback_rw on session_feedback for all to authenticated
  using (exists (select 1 from training_sessions s
                 where s.id = session_feedback.session_id
                   and s.user_id = auth.uid()::text))
  with check (exists (select 1 from training_sessions s
                      where s.id = session_feedback.session_id
                        and s.user_id = auth.uid()::text));

-- threads/messages: owner-only private AI conversations.
drop policy if exists threads_rw on chat_threads;
create policy threads_rw on chat_threads for all to authenticated
  using (auth.uid()::text = user_id) with check (auth.uid()::text = user_id);

drop policy if exists messages_rw on chat_messages;
create policy messages_rw on chat_messages for all to authenticated
  using (exists (select 1 from chat_threads t
                 where t.id = chat_messages.thread_id
                   and t.user_id = auth.uid()::text))
  with check (exists (select 1 from chat_threads t
                      where t.id = chat_messages.thread_id
                        and t.user_id = auth.uid()::text));

-- DMs: only conversation members; sender must be the authenticated user.
drop policy if exists dm_members_read on dm_members;
create policy dm_members_read on dm_members for select to authenticated
  using (exists (select 1 from dm_members m
                 where m.conversation_id = dm_members.conversation_id
                   and m.user_id = auth.uid()::text));

drop policy if exists dm_conv_read on dm_conversations;
create policy dm_conv_read on dm_conversations for select to authenticated
  using (exists (select 1 from dm_members m
                 where m.conversation_id = dm_conversations.id
                   and m.user_id = auth.uid()::text));

drop policy if exists dm_messages_read on dm_messages;
create policy dm_messages_read on dm_messages for select to authenticated
  using (exists (select 1 from dm_members m
                 where m.conversation_id = dm_messages.conversation_id
                   and m.user_id = auth.uid()::text));

drop policy if exists dm_messages_insert on dm_messages;
create policy dm_messages_insert on dm_messages for insert to authenticated
  with check (sender_id = auth.uid()::text
              and exists (select 1 from dm_members m
                          where m.conversation_id = dm_messages.conversation_id
                            and m.user_id = auth.uid()::text));

drop policy if exists dm_messages_update on dm_messages;
create policy dm_messages_update on dm_messages for update to authenticated
  using (exists (select 1 from dm_members m
                 where m.conversation_id = dm_messages.conversation_id
                   and m.user_id = auth.uid()::text));
