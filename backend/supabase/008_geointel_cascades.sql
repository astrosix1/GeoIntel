-- GeoIntel saved cascade scenarios: the trigger a user asked about and the result they saw, so a scenario can be reopened and
-- compared later. Apply in the Supabase SQL editor after 001_geointel_profiles.sql (any time after the other GeoIntel tables).
--
-- Row level security is enabled with NO policies on purpose, as in 002 to 007: only GeoIntel's backend (service-role key, verified
-- user id, premium enforced server-side) can read or write this table. The backend limits each user to 20 saved scenarios.

create table if not exists public.geointel_cascades (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  name       text not null check (char_length(name) between 1 and 80),
  request    jsonb not null check (jsonb_typeof(request) = 'object'),
  result     jsonb not null check (jsonb_typeof(result) = 'object'),
  created_at timestamptz not null default now()
);

create index if not exists geointel_cascades_user_idx
  on public.geointel_cascades (user_id, created_at desc);

alter table public.geointel_cascades enable row level security;
