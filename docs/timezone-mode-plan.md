# Time Zone mode: next features

Plan for the next round of Time Zone mode work. Everything here runs in the browser on free data and needs no backend, no API key and no new licence, apart from one small bundled cities list (see Stage 1). Earlier phases are in `docs/roadmap-phases-1-21-archive.md`. Weather mode's plan is in `docs/weather-mode-plan.md`.

Status: **Stages 1 (92ad9cd), 2 (ee0e15d) and 3 (95e8008) committed. Stage 4 implemented** (not committed); Stage 5 planned.

Stage 1 as built, and where it differs from the plan below:
- **No cities file yet.** The plan called for a bundled GeoNames list. That needs a download and an agreed attribution, so Stage 1 uses the zone names the browser already knows (about 418 `Region/City` ids, so one city per zone, no country and no population ranking) with no download and no licence. The panel says so. A real cities list can replace the search source later without changing the rest. Some browsers still report old names (Asia/Calcutta, Europe/Kiev); `MODERN_NAMES` in `lib/timezones.ts` maps them to the current ones so a search for Kolkata or Kyiv works.
- `lib/timezones.ts` (offsets, daylight saving, same-rules scan, clock readings, search), `lib/clocks.ts` (pinned clocks and display options in this browser), `sidebars/WorldClock.tsx` (left panel: pinned clocks, 12/24 hour and date format, city search), `sidebars/analysis/ZoneAnalysis.tsx` (offset, daylight-saving state, local time, places with the same rules, Pin this clock). The map popup stays and now points to the panel, because the side panels only open on hover.
- "Daylight saving" means the offset changes for most of a season. A change lasting only a few weeks (Morocco's Ramadan rule) is shown as "Offset changes for a few weeks of the year".
- Tests: `npm test` runs `frontend/tests/timezones.test.ts` (22 tests) on Node's built-in runner, no new dependency. Checked in the browser: clocks for Tokyo, New York and Kathmandu match UTC plus offset, survive a reload, and a click over Nigeria opens Lagos (UTC+1, 12 same-rule places).

## What exists today

- `frontend/src/globe/TimezoneLayer.tsx` draws the boundaries from `frontend/public/timezones.geojson`: 65 polygons, 2.4 MB, from timezone-boundary-builder release 2026d (OpenStreetMap-based, ODbL), simplified with mapshaper. The file is the "now" variant: zones that currently share identical offset and daylight-saving rules are merged, so a polygon carries only a `tzid` such as `Asia/Tokyo` and nothing else (no name, no country, no city).
- Clicking a zone shows a map popup with the zone id and its current local time, from the browser's `Intl.DateTimeFormat`. No backend call.
- `lib/units.ts` already has a Local / UTC choice for forecast times, remembered in the browser.
- The mode is wired in `globe/Globe.tsx` (layer added only in `timezone` mode, click and hover handlers) and `globe/ModeSwitcher.tsx`.

Stage 2 as built, and where it differs from the plan below:
- `lib/sun.ts` (NOAA solar-position equations; no network, no library): sun position, subsolar point, sun altitude, sunrise, sunset, day length, and the night polygon. Tests in `frontend/tests/sun.test.ts` (20 tests) check declination at the solstices and equinoxes, the equation of time, and sunrise and sunset against Open-Meteo's archive for London, Sydney, Quito, Honolulu and Nairobi (all within 3 minutes), plus polar day and night for Tromso. The night polygon is also checked against the sun altitude on a grid of 400+ points.
- Night side drawn as a translucent shade with a sunrise/sunset line (`globe/nightLayer.ts`), redrawn each minute and when the slider moves. A **Night** toggle (on by default) sits in the new time bar, so it can be switched off on slower phones.
- **Time slider** (up to a day either way, 15-minute steps, "Now" button). The clocks, the zone panel and the night shading all follow it, and the bar turns amber and says "not now" whenever it is moved.
- **Sun block** in the zone panel for the clicked point: sun up or down with its height, sunrise, sunset and daylight in the zone's own time, and polar day or night stated. Live check: a click in northern Nigeria gave 05:10 and 17:08 UTC, identical to Open-Meteo for that point.
- Not built: the optional twilight band (the plan listed it as optional). The terminator is the sunrise/sunset line only.

Stage 3 as built, and where it differs from the plan below:
- `lib/planner.ts` (all the logic, tested in `frontend/tests/planner.test.ts`, 27 tests) and two new tabs in the left panel, **Meeting planner** and **Convert**, next to **Clocks**.
- **Planner:** pick a pinned place and a date; 24 rows of that place's day, one column per pinned place showing its own local time, coloured as working hours, early or late, or night (working hours default 09:00 to 18:00, changeable and remembered). A "+1" or "-1" marks a different date. Click an hour to see each place's start and end for a 30 to 120 minute meeting, with the worst kind of hour it touches. An hour skipped by a clock change is shown as skipped. Copy as text gives one line per place.
- **Converter:** understands "14:00 UTC", "9am New York", "2026-11-02 17:30 Tokyo", "17:30 Asia/Tokyo", "noon London", "tomorrow 9am Tokyo" and "14:00 UTC+5:30". Anything else is refused with a reason: abbreviations such as CST or IST (they mean different things in different places), unknown or ambiguous places ("San"), impossible times and dates, and a time that clocks skip. A time that happens twice when clocks go back is accepted and says the first one was used.
- **Daylight-saving warnings** are given where a pair of places has a different gap three weeks before or after the chosen moment, which flags the weeks around a clock change (for example the US and UK being out of step in March and again in late October). They do not flag ordinary seasonal differences.
- Checked in the browser with London, Tokyo and New York: 10:00 in London on 3 Nov is 19:00 in Tokyo and 05:00 in New York, and the notes appear for the right weeks.

Stage 4 as built, and where it differs from the plan below:
- **Clock changes:** `lib/dst.ts` finds the last and next clock change for any zone by scanning the browser's own tz data (no table), to the minute: "Sun 1 Nov 2026, 02:00 to 01:00 (clocks back 1 h)". Shown in the zone panel (Next and Last) and as one line under each pinned clock ("Clocks go back 1 h on 1 Nov", or "no clock change in the next 14 months"). Tested on New York, London, Sydney (southern hemisphere), Lord Howe (a 30 minute change), zones that never change, and Morocco's few-week change.
- **Events in local time, worded honestly.** GDELT's timestamp is when the first article was added to the feed, not when the incident happened, and ACLED gives only a date. So the plan's "event happened at 02:40 local" is **not** shown. The event panel says "First reported at 01:30 local time (night there) ... This is when the report appeared, not necessarily when it happened", and only for news-feed events (ids starting `gdelt_`); a coarse pin is marked approximate. The zone comes from `lib/zoneLookup.ts` (point in the boundary file's polygons, tested against the real file for eight cities, ocean points and speed).
- **Filter:** a "Reported at night (local time)" button in the Events list (22:00 to 05:00 at the event's own pin) filters both the list and the globe. It only judges news-feed events with a city-level or better location; the caption says how many others are left out. On the dev data: 693 of 4,092 events, with 1,623 left out.
- Tests: `frontend/tests/dst.test.ts` and `zoneLookup.test.ts`; 94 frontend tests in all.

## Principles

- **Real data only.** Times come from the browser's own tz database (`Intl`), which carries the full daylight-saving rules. Nothing is estimated or typed in by hand, except the cities list, which is plain reference data and says where it came from.
- **Free and in the browser.** No new server work, so no new rate limits or costs.
- **Say what the data is.** Boundaries come from OpenStreetMap-based data and are simplified; the panel says so, and says when a place sits near a boundary.
- **Accessible and light.** The day/night shading and clocks must work on the phones the app already supports (the lite-device path used for radar), and respect reduced motion.
- **Each stage is checked before the next:** unit tests where there is logic, a live browser check, then move on.

## Stage 1: Reference data, zone panel and world clock

The base the other stages use.

- **Cities list.** A small bundled file (`frontend/public/cities.json`, a few thousand places) of name, country, `tzid`, latitude and longitude, built once from a free, openly licensed source. GeoNames cities with a population of at least 15,000 (CC BY 4.0) is the likely choice; confirm the licence and the attribution wording before shipping. The file is built by a script kept in `scripts/`, not hand-edited, and loaded only when Time Zone mode opens. Places whose zone is not one of the 65 merged polygons are mapped to the polygon that shares their current rules.
- **Zone detail panel** (replaces the popup). Click a zone to open it in the right sidebar: offset from UTC, whether it observes daylight saving and whether it does right now, current local date and time, the largest cities in it, and the countries it covers. All derived from `Intl` and the cities list. A line says the boundary is simplified and from OpenStreetMap-based data.
- **World clock.** Pin up to eight places (search the cities list, or add the zone you clicked). A strip of clocks shows each place's local time, the day relative to UTC (for example "tomorrow") and the offset. Remembered in the browser; for premium users, offered next to the watchlist places so a saved place is one click away (no new server storage in this stage).
- **Clock display choices:** 12 or 24 hour and date format, remembered like the weather units.
- **Honest states:** if the zone file or cities list fails to load, say so and keep the rest working.
- **Tests:** offset and daylight-saving detection across known cases (a zone with no daylight saving, one with it on, one with it off, a half-hour zone), city search, mapping of a city to a polygon, persistence with storage blocked.
- **Done when:** clicking a zone opens the panel with the right offset and cities, and two or more pinned places show correct, ticking clocks.

## Stage 2: Day and night

- **Sun maths.** A small tested module that returns the sun's position (declination and the subsolar longitude) for any instant, using the standard solar-position equations. No library and no network.
- **Night shading and terminator.** Draw the night side as a translucent polygon with a soft edge, plus an optional line for the twilight limit. Updated each minute (not each frame), so it is cheap. On lite devices, a still image refreshed each minute; no animation when reduced motion is requested.
- **Time slider.** Move the map to any hour of the next or previous 24 hours, with a "Now" button, so the terminator can be seen moving. All clocks and panels follow the chosen moment and show it plainly ("showing Tue 14:00 UTC, not now").
- **Sunrise, sunset and day length** for a clicked place, from the same maths. Polar day and polar night are stated as such, not shown as blank.
- **Tests:** known sun positions on the equinoxes and solstices, the terminator crossing the date line, polar cases, the time slider offset.
- **Done when:** the night side matches a known reference time (for example the 21 September equinox at 12:00 UTC), and sunrise and sunset for a few real cities fall within a minute or two of published values.

## Stage 3: Meeting planner and time converter

- **Planner.** Pick a set of pinned places and a date; a grid shows 24 hours down the side and one column per place, each hour marked as working hours (09:00 to 17:59), early or late (06:00 to 08:59, 18:00 to 21:59) or night, in that place's own time. The user can drag a window and read everyone's local time for it. Working hours are a default the user can change.
- **Converter.** A text box accepts forms such as "14:00 UTC", "9am New York", "2026-11-02 17:30 Tokyo" and shows the same moment in every pinned place. The parser handles a small, documented set of formats and says "I couldn't read that" instead of guessing. Ambiguous words (for example "CST") are rejected with a note, not interpreted.
- **Daylight-saving warnings.** When a chosen date falls in a window where a pinned place's offset differs from its usual relationship to another pinned place (for example the two or three weeks when the US and Europe have changed clocks on different dates), say so beside the result.
- **Copy as text:** one line per place ("Tokyo 23:00 Tue 5 Nov") for pasting into an email or a calendar invite.
- **Tests:** the converter across formats and error cases, ambiguous abbreviations, the daylight-saving gap and fold hours (clocks going forward and back), a meeting across the date line.
- **Done when:** a user can pick three cities, choose a date, and copy a correct set of local times, including on a day when one city changes its clocks.

## Stage 4: Daylight-saving awareness and events by local time

- **Daylight-saving calendar.** For each pinned place, the date and time of the last and the next clock change, found by scanning `Intl` offsets forward and back (no hand-kept table). A zone with no daylight saving says so.
- **Events in local time.** The event panel shows "Local time 02:40, night" for an event, using the zone of its pin. Only when the pin is city level or better (the same `location_confidence` rule as the hazard links); otherwise it says the local time is approximate. A filter on the events list for "night-time events" (local 22:00 to 05:00). Server-side pins and the zone file are both already available; the zone lookup is done in the browser with a point-in-polygon check against the zone file.
- **Tests:** next and previous clock change for known zones (including southern-hemisphere zones and zones that changed rules recently), the night filter at its edges, the zone lookup near a boundary and across the date line.
- **Done when:** an event in a daylight-saving zone shows the correct local time on both sides of a clock change.

## Stage 5: Map labels, links and polish

- **Time labels on the map.** Show each zone's current time or offset on the globe itself (at zoomed-out levels, one label per zone; labels thin out as the user zooms so they never overlap).
- **Date line and half-hour zones.** Gentle marking of the date line and of zones with unusual offsets (UTC+5:45, UTC+8:45, UTC+12:45 and similar), with a one-line explanation in the panel.
- **Shareable links.** `?view=timezone&zone=Asia/Tokyo` or `&clocks=Asia/Tokyo,Europe/London` opens the mode on a zone or a set of clocks, validated and then removed from the address bar, using the same pattern as the Weather links (`lib/shareLink.ts`, `state/useShareLink.ts`), including a notice if a zone name is not recognised.
- **Tests:** link parsing and rejection of invalid zone names, label thinning logic.

## Out of scope

Historical zone changes (the zone file is deliberately the current-offsets variant), live GPS or a user's own location, calendar integration, advice on the best time to do anything, and any paid time-zone service.

## Open questions to settle before building

- Which cities source and licence. GeoNames (CC BY 4.0, needs attribution) is the likely choice. The attribution text and where it appears need agreeing.
- How many cities to include, which sets the file size. A few thousand places is a few hundred kilobytes; the whole world is much larger. Population 15,000 and above is a starting point.
- Whether the world clock and pinned places should be saved to the user's account (needs a Supabase table and SQL for premium users) or stay in the browser. This plan keeps them in the browser; saving is a later, separate step.
- Default working hours for the planner (09:00 to 17:59 is assumed).
- Whether the day and night shading should be on by default or behind a toggle, given the cost on low-end phones.

## Build order and why

1. Stage 1 first: the cities list and the panel are used by every later stage.
2. Stage 2 is independent after that and can move up if the day and night view matters most.
3. Stage 3 needs Stage 1 only.
4. Stage 4 needs Stage 1, and its event part reuses the zone lookup written for Stage 1.
5. Stage 5 is additive and last.

## Testing each stage

- Unit tests for every piece of logic (offsets, sun position, parsing, daylight-saving scans), using dates with known right answers.
- Backend suite, `tsc`, lint and the production build stay green. Time Zone mode needs no backend change, so the backend suite is a regression check only.
- A live check in the browser pane before moving on: a zone panel, pinned clocks, the terminator at a known time, and a converter run, with the dev clock checked against a reference.

## Owner actions

- Confirm the cities source and its attribution wording (Stage 1).
- Decide whether pinned places should be saved to accounts (affects whether a Supabase SQL file is needed later).
- No new keys, services or migrations are needed for any stage as planned.
