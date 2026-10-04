-- GeoIntel watchlist: places a user wants hazard alerts for, the alerts raised
-- for them, and the alert settings. Apply in the Supabase SQL editor after
-- 002_geointel_user_data.sql (it adds columns to geointel_user_prefs).
--
-- Row level security is enabled with NO policies on purpose, as in 002/003:
-- only GeoIntel's backend (service-role key, verified user id, premium
-- enforced server-side) can read or write these tables.

create table if not exists public.geointel_watch_places (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  name       text not null check (char_length(name) between 1 and 80),
  lat        double precision not null check (lat between -90 and 90),
  lon        double precision not null check (lon between -180 and 180),
  radius_km  integer not null check (radius_km between 10 and 2000),
  created_at timestamptz not null default now()
);

create index if not exists geointel_watch_places_user_idx
  on public.geointel_watch_places (user_id, created_at);

-- One place name per user, ignoring case.
create unique index if not exists geointel_watch_places_user_name_uniq
  on public.geointel_watch_places (user_id, lower(name));

create table if not exists public.geointel_alerts (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  place_id    uuid not null references public.geointel_watch_places (id) on delete cascade,
  -- "<type>-<id>-<alert level>": a hazard that escalates (Green to Orange)
  -- gets a new key and so alerts again; the same hazard at the same level
  -- never alerts twice for one place.
  hazard_key  text not null,
  hazard_type text not null,
  title       text not null,
  alert_level text not null,
  distance_km numeric not null,
  created_at  timestamptz not null default now(),
  read_at     timestamptz,
  emailed_at  timestamptz,
  unique (place_id, hazard_key)
);

create index if not exists geointel_alerts_user_created_idx
  on public.geointel_alerts (user_id, created_at desc);

-- Alerts still waiting for an email (the evaluator retries these).
create index if not exists geointel_alerts_unemailed_idx
  on public.geointel_alerts (created_at) where emailed_at is null;

alter table public.geointel_user_prefs
  add column if not exists alert_email boolean not null default true,
  add column if not exists alert_min_level text not null default 'orange'
    check (alert_min_level in ('green', 'orange', 'red'));

alter table public.geointel_watch_places enable row level security;
alter table public.geointel_alerts       enable row level security;
