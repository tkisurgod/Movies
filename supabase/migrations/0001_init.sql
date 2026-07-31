-- ============================================================================
-- TK Entertainment — Supabase initial schema
--
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- Safe to re-run (idempotent).
--
-- Covers REVAMP.md §4.2 — profiles, watch_progress, concierge_sessions.
-- ============================================================================


-- ============================================================================
-- Shared helper: keep updated_at honest
-- ============================================================================
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;


-- ============================================================================
-- profiles — one row per auth.users row, created automatically on signup
-- ============================================================================
create table if not exists public.profiles (
  id           uuid primary key references auth.users on delete cascade,
  display_name text,
  avatar_url   text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles: read own" on public.profiles;
create policy "profiles: read own" on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "profiles: update own" on public.profiles;
create policy "profiles: update own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

-- Auto-provision a profile whenever someone signs up.
-- security definer: runs as the function owner so it can write past RLS.
-- search_path pinned to '' to prevent search-path hijacking.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, split_part(new.email, '@', 1))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- ============================================================================
-- watch_progress — one row per (user, title, season, episode)
--
-- season/episode default to 0 rather than NULL so they participate in the
-- primary key. Postgres treats NULLs as distinct, which would otherwise let
-- duplicate movie rows pile up for the same title.
-- ============================================================================
create table if not exists public.watch_progress (
  user_id          uuid    not null references auth.users on delete cascade,
  tmdb_id          integer not null,
  media_type       text    not null check (media_type in ('movie', 'tv')),
  season           integer not null default 0,   -- 0 for movies
  episode          integer not null default 0,   -- 0 for movies
  is_anime         boolean not null default false,

  position_seconds numeric not null default 0 check (position_seconds >= 0),
  duration_seconds numeric check (duration_seconds is null or duration_seconds > 0),
  progress_pct     numeric generated always as (
                     case
                       when duration_seconds is not null and duration_seconds > 0
                       then least(100, round((position_seconds / duration_seconds) * 100, 2))
                       else 0
                     end
                   ) stored,
  completed        boolean not null default false,

  title            text,
  poster_path      text,
  source           text,          -- which embed provider reported this

  -- How the position was obtained. The UI must not promise an exact
  -- timestamp when this is 'coarse'. See REVAMP.md §4.4.
  --   exact  → provider postMessage API (real playhead)
  --   coarse → wall-clock heartbeat estimate
  --   none   → no position captured; season/episode only
  fidelity         text not null default 'none'
                     check (fidelity in ('exact', 'coarse', 'none')),

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  primary key (user_id, tmdb_id, media_type, season, episode)
);

create index if not exists watch_progress_recent_idx
  on public.watch_progress (user_id, updated_at desc);

alter table public.watch_progress enable row level security;

drop policy if exists "watch_progress: own rows" on public.watch_progress;
create policy "watch_progress: own rows" on public.watch_progress
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists watch_progress_touch on public.watch_progress;
create trigger watch_progress_touch before update on public.watch_progress
  for each row execute function public.touch_updated_at();


-- ============================================================================
-- continue_watching — latest unfinished row per title
--
-- watch_progress stores one row per episode so a user can be mid-way through
-- S1E4 and S3E2 independently. The Continue Watching rail wants one card per
-- show, so collapse to the most recently touched episode.
--
-- security_invoker = on is load-bearing: without it the view runs as its
-- owner and would bypass the RLS policy above, exposing every user's rows.
-- ============================================================================
create or replace view public.continue_watching
with (security_invoker = on) as
select distinct on (user_id, tmdb_id, media_type) *
from public.watch_progress
where completed = false
order by user_id, tmdb_id, media_type, updated_at desc;


-- ============================================================================
-- concierge_sessions — AI Concierge past picks (replaces localStorage)
-- ============================================================================
create table if not exists public.concierge_sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users on delete cascade,
  movie_id    integer,
  movie_title text,
  stream_url  text,
  messages    jsonb not null default '[]'::jsonb,
  ended_at    timestamptz not null default now()
);

create index if not exists concierge_sessions_recent_idx
  on public.concierge_sessions (user_id, ended_at desc);

alter table public.concierge_sessions enable row level security;

drop policy if exists "concierge_sessions: own rows" on public.concierge_sessions;
create policy "concierge_sessions: own rows" on public.concierge_sessions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
