-- GeoIntel event comments and their moderation reports.
-- Apply in the Supabase SQL editor (after 001 and 002).
--
-- Like 002, row level security is enabled with NO policies: only GeoIntel's
-- backend (service-role key) can read or write these tables, and it enforces
-- who may post, report or delete. Reading comments is public, but it goes
-- through the backend, which decides what each viewer is allowed to see.

-- Display names are shown next to comments, so they must be unique ignoring
-- case; otherwise anyone could pose as another user.
create unique index if not exists geointel_profiles_display_name_ci
  on public.geointel_profiles (lower(display_name));

create table if not exists public.geointel_comments (
  id           uuid primary key default gen_random_uuid(),
  crisis_id    text not null,
  user_id      uuid not null references public.geointel_profiles (user_id) on delete cascade,
  -- Snapshot of the author's display name at post time: no join needed to list
  -- comments, and old comments stay readable if the name later changes.
  author_name  text not null,
  body         text not null check (char_length(body) between 1 and 1000),
  -- visible: shown to everyone. hidden: auto-hidden after enough reports; shown
  -- only to its author and the admin until reviewed. removed: never served.
  status       text not null default 'visible' check (status in ('visible', 'hidden', 'removed')),
  report_count integer not null default 0,
  created_at   timestamptz not null default now()
);

create index if not exists geointel_comments_crisis_created_idx
  on public.geointel_comments (crisis_id, created_at desc);
create index if not exists geointel_comments_status_idx
  on public.geointel_comments (status, created_at desc);

create table if not exists public.geointel_comment_reports (
  comment_id  uuid not null references public.geointel_comments (id) on delete cascade,
  reporter_id uuid not null references auth.users (id) on delete cascade,
  reason      text,
  created_at  timestamptz not null default now(),
  -- One report per person per comment, so the count means distinct people.
  primary key (comment_id, reporter_id)
);

alter table public.geointel_comments        enable row level security;
alter table public.geointel_comment_reports enable row level security;
