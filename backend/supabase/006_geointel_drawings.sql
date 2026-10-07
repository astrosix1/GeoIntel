-- GeoIntel saved drawings: the shapes, layers and notes a premium user draws on the map.
-- Apply in the Supabase SQL editor (after 001_geointel_profiles.sql; this file is safe to run more than once).
--
-- Row level security is enabled with NO policies on purpose, exactly as for the other GeoIntel tables: that denies every
-- request made with a user's (or the anon) key, so only GeoIntel's backend (service-role key, which verifies the user's
-- JWT and enforces premium) can read or write it, always scoped to the verified user id.

create table if not exists public.geointel_drawings (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  name        text not null check (char_length(name) between 1 and 80),
  -- {"version": 1, "layers": [...], "features": [GeoJSON features]}, validated and cleaned by the backend before it is stored.
  data        jsonb not null,
  -- Kept beside the blob so the list of a user's drawings does not have to load every drawing.
  shape_count integer not null default 0,
  layer_count integer not null default 1,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists geointel_drawings_user_updated_idx
  on public.geointel_drawings (user_id, updated_at desc);

alter table public.geointel_drawings enable row level security;
