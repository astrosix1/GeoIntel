-- GeoIntel dashboard data: saved events and per-user preferences.
-- Apply in the Supabase SQL editor (after 001_geointel_profiles.sql).
--
-- Row level security is enabled with NO policies on purpose: that denies every
-- request made with a user's (or the anon) key, so only GeoIntel's backend —
-- which uses the service-role key, verifies the user's JWT and enforces
-- premium — can read or write these tables, always scoped to the verified
-- user id. Users cannot reach them directly.

create table if not exists public.geointel_saved_events (
  user_id     uuid not null references auth.users (id) on delete cascade,
  crisis_id   text not null,
  -- Snapshot taken server-side from GeoIntel's own crisis row at save time, so
  -- the entry survives the event being archived out of the live list.
  title       text not null,
  country     text,
  type        text,
  severity    integer,
  lat         double precision,
  lon         double precision,
  source_url  text,
  event_date  timestamptz,
  saved_at    timestamptz not null default now(),
  primary key (user_id, crisis_id)
);

create index if not exists geointel_saved_events_user_saved_idx
  on public.geointel_saved_events (user_id, saved_at desc);

create table if not exists public.geointel_user_prefs (
  user_id        uuid primary key references auth.users (id) on delete cascade,
  -- Outlet hostnames (lowercase, no leading www.) whose events the user hides.
  hidden_outlets text[] not null default '{}',
  updated_at     timestamptz not null default now()
);

alter table public.geointel_saved_events enable row level security;
alter table public.geointel_user_prefs   enable row level security;
