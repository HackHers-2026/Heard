-- Heard initial schema
-- Run via Supabase SQL editor or MCP apply_migration

create extension if not exists "pgcrypto";

create table if not exists "user" (
  id          text primary key default gen_random_uuid()::text,
  linkedin_id text,
  name        text not null,
  avatar_url  text,
  career_tag  text,
  is_mentor   boolean not null default false,
  created_at  text not null default now()::text
);

create table if not exists speech (
  id         text primary key default gen_random_uuid()::text,
  user_id    text not null references "user"(id),
  status     text not null default 'live',
  started_at text not null default now()::text,
  ended_at   text
);

create table if not exists speechmetrics (
  id                 text primary key default gen_random_uuid()::text,
  speech_id          text not null references speech(id),
  clarity            integer not null default 0,
  volume             integer not null default 0,
  pace               integer not null default 0,
  confidence         integer not null default 0,
  structure          integer not null default 0,
  overall            integer not null default 0,
  summary            text not null default '',
  suggestions        text not null default '[]',
  mentor_suggestions text not null default '[]'
);

create table if not exists realtimesegment (
  id               text primary key default gen_random_uuid()::text,
  speech_id        text not null references speech(id),
  transcript       text not null,
  nudge            text not null default '',
  segment_index    integer not null,
  recorded_at      text not null,
  duration_seconds real not null,
  avg_volume       integer not null default 0,
  volume_variance  integer not null default 0
);

create table if not exists communitypost (
  id         text primary key default gen_random_uuid()::text,
  speech_id  text not null references speech(id),
  user_id    text not null references "user"(id),
  is_public  boolean not null default true,
  career_tag text,
  topic_tag  text,
  like_count integer not null default 0,
  created_at text not null default now()::text
);

create table if not exists "like" (
  id         text primary key default gen_random_uuid()::text,
  post_id    text not null references communitypost(id),
  user_id    text not null references "user"(id),
  created_at text not null default now()::text
);

create table if not exists mentorconnection (
  id           text primary key default gen_random_uuid()::text,
  requester_id text not null references "user"(id),
  mentor_id    text not null references "user"(id),
  speech_id    text not null references speech(id),
  status       text not null default 'pending',
  created_at   text not null default now()::text
);
