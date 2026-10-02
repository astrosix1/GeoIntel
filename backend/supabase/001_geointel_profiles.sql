-- GeoIntel public profile (display name / avatar shown next to comments, pins,
-- follows). Named geointel_profiles so it can't collide with any shared
-- `profiles` table asix.live may already have. Apply in the Supabase SQL editor.

create table if not exists public.geointel_profiles (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  display_name text not null check (char_length(display_name) between 2 and 40),
  avatar_url   text,
  created_at   timestamptz not null default now()
);

alter table public.geointel_profiles enable row level security;

-- Display names/avatars are public (they appear beside comments and pins).
create policy "geointel_profiles are readable by everyone"
  on public.geointel_profiles for select
  using (true);

-- A user can only create or change their own row.
create policy "users insert their own geointel profile"
  on public.geointel_profiles for insert
  with check (auth.uid() = user_id);

create policy "users update their own geointel profile"
  on public.geointel_profiles for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
