-- GeoIntel per-place alert choices: which kinds of alert each watched place raises (for example storms and
-- floods but not droughts, and the minimum level). Stored as one JSON object per place, for example
--   {"hazards": {"types": ["TC", "FL"], "min_level": "red"}}
-- An empty object means the defaults (every hazard type, at the account's minimum level), so places that
-- already exist keep working. Apply in the Supabase SQL editor after 004_geointel_watchlist.sql. The backend
-- validates every value before saving it.

alter table public.geointel_watch_places
  add column if not exists alert_prefs jsonb not null default '{}'::jsonb
    check (jsonb_typeof(alert_prefs) = 'object');
