-- GeoIntel weather-condition alerts: the limits a user sets (heat, cold, heavy rain,
-- strong gusts, UV), stored as one JSON object per user, for example
--   {"heat_c": 38, "rain_mm": 80}
-- An empty object means no condition alerts. Apply in the Supabase SQL editor after
-- 004_geointel_watchlist.sql. The backend validates every value before saving it.

alter table public.geointel_user_prefs
  add column if not exists alert_conditions jsonb not null default '{}'::jsonb
    check (jsonb_typeof(alert_conditions) = 'object');
