# Choose your alerts, per place, with badges

Plan for letting each user pick which alerts they get for each watched place, and for showing a badge when one arrives. Nothing here is built yet.

## What exists today

- A watched place has a name, a point and a radius (10 to 2,000 km).
- **Hazard alerts** (every 15 minutes): any live GDACS hazard inside the radius at or above one **account-wide** minimum level (Green, Orange, Red). All hazard types are treated alike.
- **Forecast limit alerts** (hourly): heat, cold, heavy rain, UV, set once per account and applied to every place.
- One account-wide email switch. Emails go out only when the mail keys are set on Railway.
- The Alerts tab lists alerts; the Dashboard button carries one unread count, refreshed every 5 minutes.

So a user cannot say "storms yes, earthquakes no" or "tell me about this place but not that one", and there is nothing for news situations or clock changes.

## What the user chooses

Per place, a short list of switches grouped like this. Each place starts with a sensible default (hazards on, the rest off), and a "same as my other places" shortcut sets them all.

**Natural hazards** (the live hazard feed already used by Weather mode)
- Tropical cyclones and storms
- Floods
- Earthquakes
- Volcanoes
- Wildfires
- Droughts
- Minimum level for these: Green, Orange or Red (per place, replacing the one account-wide level)

**Weather limits** (the forecast checks that exist)
- Heat, cold, heavy rain, UV, each with its own limit (per place, replacing the account-wide limits)

**Situations** (new)
- "A situation starts near this place": a news situation (stories grouped by the situation feature) or a new serious event whose pin falls inside the radius. Choices: minimum severity (Serious, Severe, Critical) and whether it counts statements and talks or only physical events.

**Clock changes** (new)
- "The clocks change at this place" within the next 7 days (daylight saving starts or ends), using the place's own time zone. One alert per change.

**Delivery**
- In the app always; by email on or off per category group (the existing email switch stays as the master).

## Badges

- **Dashboard button:** the existing unread count, now refreshed faster (every minute) and also when the tab regains focus.
- **Alerts tab label:** the count, as now, with a small coloured dot by alert level (red if any unread alert is Red).
- **Each place in the Watchlist:** a small count of its unread alerts.
- **Each alert in the list:** a "new" marker until it is read, plus its category icon.
- **Opening it:** an alert that points at a hazard or event opens it on the map, and is marked read.

No sound and no phone push (the app has no push set up).

## How it is built

- **Data:** one new Supabase column on `geointel_watch_places`, `alert_prefs` (JSON), added by a new SQL file `007_geointel_place_alert_prefs.sql`. An empty value means "defaults", so existing places keep working. Alerts gain a `category` column (hazard, weather, situation, clock) so the list can filter and badge by it.
- **Server:** the hazard evaluator reads each place's own prefs (types and level) instead of the account level. The forecast evaluator reads per-place limits, falling back to the account limits for places that have none. Two new evaluators: situations (reads the situations and new events the app already holds, no new feed) and clock changes (reads the time zone data already bundled). Dedupe stays the database's job through the unique key, with the category in the key.
- **Validation:** every pref is checked on the server (known types only, levels from a fixed list, limits within ranges), as the existing settings are.
- **Screen:** each place in the Watchlist opens a small "Alerts for this place" panel with the switches above. The Alerts tab gets filter chips by category and the unread markers.
- **Tests:** per-place filtering (a place with storms off gets no storm alert), situation and clock-change evaluators with fixtures, dedupe, validation, and the badge counts.

## Stages

1. **Per-place hazards and badges:** the new column, per-place hazard types and level, the panel, unread badges (per place, tab, button) and faster refresh.
2. **Per-place weather limits.**
3. **Situation alerts.**
4. **Clock-change alerts.**

Each ends with tests, a browser check and the usual "commit and continue".

## Risks

- **Supabase setup:** this needs one more SQL file run in your Supabase, as 004 and 005 did.
- **Volume:** situation alerts could be noisy near busy places. Defaults are off, the minimum severity is Serious or higher, and one alert covers a whole situation, not each story in it.
- **Email:** category switches change the digest, and it still only sends once the mail keys are set.
- **Local history:** there is no past data, so existing alerts keep their old (hazard) category.

## Decisions needed

1. **Per place or one set for the account?** Recommended: per place, with a "same as my other places" shortcut.
2. **Situations:** is "a situation or serious event starts inside the radius" what you mean, and is Serious as the lowest level right?
3. **Clock changes:** alert 7 days ahead, once per change, as above?
4. **Badges:** is the list above enough, or do you also want a badge on the map pins of watched places?
