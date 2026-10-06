# Weather mode: next features

Plan for the next round of Weather mode work. Everything here uses free data or data the app already has, apart from the optional AI items at the end. Earlier phases are in `docs/roadmap-phases-1-21-archive.md`. The story pipeline is in `docs/story-pipeline-plan.md`.

Status: **Stage 1 implemented** (not committed). Stages 2 to 5 planned.

Stage 1 data check, done against the live GDACS feed (2026-10-05):
- *Cyclones:* per-event geometry has the track as line segments flagged past or forecast, three current wind-zone polygons (60, 90 and 120 km/h), per-time-step footprints (not used) and an uncertainty cone. Population inside the 119 km/h and 63 km/h wind buffers comes from the impact links; the value is blank when GDACS has no number, shown as "Not reported".
- *Floods:* an affected-area polygon (about 350 KB raw, simplified to about 5 KB) and authority-reported impacts (displaced, houses damaged).
- *Wildfires:* an affected-area polygon and a people-affected count.
- *Droughts:* none in the feed right now; handled as "not published".
- Built: `services/hazard_detail.py`, `GET /api/weather/storms/<type>/<id>`, `data_sources/gdacs.py` now carries `episode_id`, `globe/hazardGeometry.ts` (map layers for the selected hazard), and a Track and exposure block in `HazardAnalysis`. Live-checked in the browser for a cyclone (path, wind zones, cone and population figures shown).

## What exists today

- **Hazards:** `data_sources/gdacs.py` reads the GDACS event feed and keeps only weather hazards (tropical cyclone, flood, wildfire, drought). Each hazard has one point (lat/lon), alert level (Green/Orange/Red), a severity value and unit, affected countries, dates and a report link. `services/weather.py` caches the list for 5 minutes. Endpoint `GET /api/weather/storms`.
- **Forecasts:** `services/forecast.py` calls Open-Meteo for a point (current, 48 hourly, daily) and is cached for 15 minutes. Endpoint `GET /api/weather/forecast`.
- **Radar:** RainViewer tiles (`globe/radarLayer.ts`, `useRadar.ts`).
- **Watchlist alerts:** `services/alerts.py` matches saved places against hazards (default minimum level Orange) and sends email.
- **Frontend:** `sidebars/analysis/HazardAnalysis.tsx`, `PointForecast.tsx`, `globe/hazards.ts`, `WeatherLegend.tsx`.

## Principles

- **Real data only.** If a feed has no track, footprint or number, we show an honest "not available", never an estimate drawn to look real.
- **Say how old it is.** Anything that can go stale shows its age.
- **Near and during, never caused by.** Links between hazards and events are spatial and time matches, labelled as such.
- **Premium rules unchanged.** Server-side gating; AI features are premium-only and on demand.
- **Each stage is checked before the next:** tests, a live check, then move on.

## Stage 1: Hazard tracks, footprints and exposure

The base the other features depend on. Today a hazard is a single dot.

- **Find the data first (a short check, before any code).** GDACS publishes per-event detail (geometry, track points, severity per point, population exposed) through its event-data API. Confirm for each hazard type what it actually returns: track and forecast points for cyclones, an affected-area polygon for floods and fires, population figures. Whatever is missing for a type stays unavailable for that type.
- **Backend:** extend `GDACSConnector` with a per-event detail fetch, cached per event and refreshed with the hazard (a changed `date_modified` triggers a refetch). Return `track` (past and forecast points, each marked as past or forecast), `footprint` (polygon where the feed gives one) and `exposure` (people affected, as the feed states it) on a new `GET /api/weather/storms/<id>`. No change to the list payload, so the map stays light.
- **Frontend:** draw the past path as a solid line and the forecast path as a dashed line with the cone or wind radius where given. Add an **Exposure** block to `HazardAnalysis` (people in the footprint and the countries affected, with the feed's wording and the date it was modified). Draw the footprint for floods and fires.
- **Tests:** parsing of real sample payloads kept as fixtures, missing-field handling, per-event caching, endpoint 404 and unavailable states.
- **Done when:** a live cyclone shows its path and exposure, and a hazard with no track shows "Track not published for this event".

## Stage 2: Forecast timeline and compare places

- **Timeline:** extend the Open-Meteo request to 7 days hourly (the code now returns 48 hours; `HOURS_SHOWN` and the field lists in `services/forecast.py`). Add a time scrubber under the map in Weather mode. Moving it updates the forecast panel for the selected place and, where tile sources allow, the radar/forecast layer. Radar itself is observed and short-range only, so the scrubber labels what is observed and what is forecast.
- **Compare:** let a user pick up to three places (from the watchlist or by search) and see them side by side: current conditions, the next 7 days, and any active hazard within the place's area. Free users can compare two places; premium three (limits to confirm).
- **Backend:** `GET /api/weather/compare?places=...` that reuses `get_forecast` per place and the stage 1 hazard geometry. Keep the existing coordinate validation and per-IP rate limits.
- **Tests:** range and cache behaviour, invalid coordinates, partial failure (one place down must not fail the others, and says so).

## Stage 3: Weather and events together

Link a hazard and an event when they share place and time. All rules, no AI.

- **Match rules**
  - *Place:* the event's pin is inside the hazard footprint, or within a distance of its track or point. Use the stage 1 geometry where it exists; otherwise a fixed radius per hazard type, shown to the user as approximate.
  - *Time:* the hazard is active at the event's date, or ended within a window (start with 3 days; tune per type).
  - *Kind:* physical events only. Statements are excluded.
  - *Precision:* only events with a city-level or better pin (`location_confidence` of 85 or more) are linked, so a country-centre pin never matches a hazard by accident.
- **Backend:** a `services/hazard_links.py` that computes links for active hazards and recent events, stored in a small table (`hazard_event_links`: hazard id, crisis id, distance in km, time gap in hours, basis) and refreshed after each sync. It follows `merged_into`, so a merged story is linked once. Return links on the event detail and hazard detail endpoints.
- **Frontend:** a **Nearby hazard** card in the event panel and an **Events in this area** list in the hazard panel, each showing distance and time gap. A small marker on linked items in both lists. An optional **Related** map toggle that draws faint lines between linked pairs (off by default). A list filter, "Events affected by hazards".
- **Wording:** "near" and "during". Never "caused by".
- **Tests:** each rule on its own (inside and outside footprint, time window edges, statements excluded, coarse pins excluded), merged stories, no links when nothing matches.

## Stage 4: Alerts and layers

- **Wider alert triggers:** extend the watchlist rules beyond GDACS hazards to heat and cold thresholds, heavy rain, air quality and UV, using Open-Meteo fields. Users set thresholds per place. Keep the alert dedupe and retry behaviour in `services/alerts.py`; a linked-events line (from stage 3) can be added to the email.
- **Extra map layers:** wind, temperature, cloud cover and pressure. Choose sources only after checking each one's commercial terms (as was needed for RainViewer). A layer without clear terms is not shipped.

## Stage 5: Polish

- **Past 24 hours:** observed rainfall and the radar loop for "what just happened here".
- **Units and time:** °C or °F, km/h or mph, local or UTC time, remembered per user.
- **Shareable links:** a URL that opens the map on a given hazard or place with the same view and layers.
- **Honest states:** radar unavailable, forecast provider down, data age, shown plainly everywhere.

## Optional AI features (need `ANTHROPIC_API_KEY`, premium, on demand)

- **Hazard briefing:** a short cited note on what is happening and who is exposed, built only from the hazard record, exposure figures and linked events.
- **Hazard scenarios:** the existing scenario machinery pointed at a hazard (landfall, weakening, turning away). No percentages, assumptions listed.
- **Plain-language alert emails:** rewrite the alert text, only for alerts that fire.
- **Linked-pair note:** how a hazard may affect access or aid where an event is ongoing, cited, with assumptions.

Cached per hazard with a stamp that changes when the hazard is updated, the same pattern as story briefings. Not worth doing: AI forecasting of the weather itself, or bulk AI on every low-alert hazard.

## Build order and why

1. Stage 1 first. Stage 3 (links) needs real footprints, and the exposure block is the single most useful addition for journalists.
2. Stage 2 and stage 3 are independent after that and can swap order.
3. Stage 4 and 5 last; they are the lowest risk and mostly additive.

## Open questions to settle before building

- What does GDACS actually return per hazard type (tracks, polygons, population)? This decides what stage 1 can promise for floods, fires and droughts.
- Time window after a hazard ends for links (3 days is a guess).
- Free versus premium limits for compare and the extra alert triggers.
- Which wind, temperature and cloud tile sources have terms that allow commercial use.
- Whether the 7-day hourly Open-Meteo request stays inside the free tier's limits at your traffic, or needs `OPEN_METEO_API_KEY`.

## Testing each stage

- Unit tests per stage, using fixture payloads copied from real feeds.
- Backend suite, `tsc`, lint and the build stay green.
- A live check in the browser pane before moving on: a real hazard with a track, exposure and linked events, and the unavailable states with a feed blocked.

## Owner actions

- Stages 1 to 3 and 5 need no new keys.
- `OPEN_METEO_API_KEY` may be needed for stage 2 and 4 at scale.
- Any new migration (the links table) runs automatically on deploy.

## Out of scope

Weather forecasting by AI, hurricane-category prediction, user-uploaded observations, push notifications to phones.
