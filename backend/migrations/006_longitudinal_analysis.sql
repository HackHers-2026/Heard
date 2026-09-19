-- Heard v3: longitudinal analysis — richer feedback columns, per-user Backboard
-- coach id, and channel-specific performance memory. Idempotent.

-- ─────────────────────────────────────────────────────────────────────────────
-- profiles: stable per-user Backboard coach assistant id
-- ─────────────────────────────────────────────────────────────────────────────
alter table profiles add column if not exists backboard_assistant_id text;

-- ─────────────────────────────────────────────────────────────────────────────
-- session_feedback: sixth dimension (conciseness) + rich longitudinal columns
-- ─────────────────────────────────────────────────────────────────────────────
alter table session_feedback add column if not exists conciseness_score      real;
alter table session_feedback add column if not exists unavailable_dimensions jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists metrics_summary        jsonb not null default '{}'::jsonb;
alter table session_feedback add column if not exists longitudinal_analysis  jsonb not null default '{}'::jsonb;
alter table session_feedback add column if not exists strongest_moments      jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists priority_moments       jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists persistent_patterns    jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists new_patterns           jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists stable_strengths       jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists next_session_goals     jsonb not null default '[]'::jsonb;
alter table session_feedback add column if not exists metrics_interpretation jsonb not null default '{}'::jsonb;
alter table session_feedback add column if not exists vocal_variety          jsonb not null default '{}'::jsonb;

-- ─────────────────────────────────────────────────────────────────────────────
-- user_channel_performance_profiles: compact channel-specific longitudinal rollup
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists user_channel_performance_profiles (
  id                    text primary key default gen_random_uuid()::text,
  user_id               text not null references profiles(id) on delete cascade,
  channel_id            text not null references channels(id) on delete cascade,
  completed_sessions    integer not null default 0,
  baseline_score        real,
  recent_score          real,
  improvement_percent   real,
  dimension_trends      jsonb not null default '{}'::jsonb,
  recurring_strengths   jsonb not null default '[]'::jsonb,
  recurring_weaknesses  jsonb not null default '[]'::jsonb,
  recent_patterns       jsonb not null default '[]'::jsonb,
  current_training_goals jsonb not null default '[]'::jsonb,
  updated_at            text not null default now()::text,
  unique (user_id, channel_id)
);
create index if not exists ix_perf_user on user_channel_performance_profiles(user_id);
create index if not exists ix_perf_channel on user_channel_performance_profiles(channel_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- RLS: performance profiles are owner-only.
-- ─────────────────────────────────────────────────────────────────────────────
alter table user_channel_performance_profiles enable row level security;
drop policy if exists perf_rw on user_channel_performance_profiles;
create policy perf_rw on user_channel_performance_profiles for all to authenticated
  using (auth.uid()::text = user_id) with check (auth.uid()::text = user_id);
