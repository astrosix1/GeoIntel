# GeoIntel roadmap archive, phases 1-21

The accumulated plan for everything built so far (all implemented). Kept for reference; the current work has its own document, `docs/story-pipeline-plan.md`.

---

# GeoIntel Rewrite v2: Real-map Globe, Dual Analysis Sidebars, Multi-Mode Views

## Context

GeoIntel's current codebase (`app.js` at 5,418 lines, `backend/app.py` at 2,745 lines, `backend/data_sources.py` at 2,754 lines — each a single file mixing many unrelated concerns, no build system, no type safety) is being rebuilt in place. An earlier pass at this plan proposed a minimal v1 (globe + crisis pins only); the product owner then provided a detailed, specific vision that supersedes that minimal scope. This plan targets that full vision directly, phased by build risk/dependency rather than cut down.

**What's being kept from the old app** (hard constraints, unchanged from the prior planning round): the "no fabricated data" discipline established this session (real severity from GDELT's GoldsteinScale, honest fallback/absent states instead of invented numbers — extended below to cover the new country-analysis and media features), the same free data sources with their live-verified GDELT parsing/filtering logic (Phases 21-23's self-referential/generic-actor/blank-actor-violent-root/demonym noise filters, ported not redesigned), and a rebuild-in-place approach (same repo).

**The new product vision** (from the product owner directly):
- A globe that pins real geo-located global events, rendered with real OpenStreetMap data — not a baked/hand-rolled texture.
- Two translucent sidebars: **Events** (left) and **Analysis** (right).
- Click a pin → Analysis slides open with an extensive analysis of that event.
- Click a country → Analysis slides open with that country's population/demographics, unique geographical/infrastructural features, vital trade routes, top production/exports, and its contribution to the world.
- Sidebars open on hover: cursor in the left 10% of the screen opens Events, right 10% opens Analysis — not click-to-toggle.
- An interactive solar-system background behind the globe, with occasional shooting stars and UFOs.
- Three globe modes: **Events** (crisis pins, the current default), **Weather** (global weather, with pins marking catastrophic storms), **Time Zone** (timezone boundary lines + current local time per zone).
- Embedded real media (images/video) in the Analysis panel where available.
- A logo at the top of the screen.

## Tech Stack

### Globe: MapLibre GL JS (globe projection) + OpenFreeMap vector tiles

This directly satisfies "uses OpenStreetMap" in a way a hand-rolled Three.js sphere (the old app's approach, and my own earlier proposal to port it via react-three-fiber) does not: **MapLibre GL JS added native globe projection in v5** — a real, actively-maintained, BSD-licensed open-source library (a community fork of Mapbox GL JS) that reprojects real Mercator vector/raster map tiles onto an actual 3D globe with atmosphere effects, via [Adaptive Composite Map Projection](https://maplibre.org/roadmap/maplibre-gl-js/globe-view/). It natively supports vector overlays, markers/popups (pins), click-to-select on real country polygons, and — confirmed via MapLibre's own example gallery — [embedding three.js 3D models directly on the globe](https://maplibre.org/maplibre-gl-js/docs/examples/add-a-3d-model-to-globe-using-threejs/), which covers the UFO/decorative-object ask without a second rendering engine.

**Tile source**: [OpenFreeMap](https://openfreemap.org/) — confirmed real, free, open-source vector-tile hosting built from actual OpenStreetMap + OpenMapTiles + Planetiler + Natural Earth data, with no API key, no registration, no request limits (donation-supported; self-hostable later if needed). Vector tiles specifically (not raster) — MapLibre's own globe documentation notes raster tiles need much higher base granularity to avoid visible warping at the globe's silhouette, so vector is the right choice for this exact use case.

This replaces the earlier plan's react-three-fiber recommendation entirely for the base globe/map layer — R3F is still the right tool for the decorative three.js overlays (UFOs, the solar-system background isn't tied to the map at all and can be a separate canvas layer behind the MapLibre canvas).

### Frontend: Vite + React + TypeScript (unchanged from the prior plan)

Same reasoning as before: a real build step + static typing is the structural fix for bug classes this session hit repeatedly (`Number(id)` coercion breaking sharing/bookmarking, a hand-written `to_dict()` silently dropping real fields). react-map-gl or a thin custom wrapper around MapLibre's JS API for the globe component; CSS Modules for the two sidebars' translucent/slide-open styling (a small, well-scoped set of components — no need for a heavier styling framework); React Query for server state (crisis list, country facts, event analysis) + Zustand for UI state (which sidebar is open, hover-zone tracking, active globe mode).

### Backend: Flask restructured into Blueprints + Pydantic schemas (unchanged from the prior plan)

Same reasoning as before — `data_sources.py`'s GDELT/ACLED/NewsAPI/WorldBank/Nominatim connector logic (including this session's live-verified noise filters) is real, hard-won domain logic to port, not redesign; a framework migration (to FastAPI) would touch every route for no functional gain. Get Pydantic's schema-validation benefit on top of Flask via **apiflask** (spike one route first; fall back to hand-written Pydantic schemas without auto-docs if friction is high). New blueprints needed for this plan's expanded scope: `crises` (events), `countries` (new — demographics/geography/trade/media), `weather` (new), `timezones` (new, likely closer to static-data-serving than a live connector).

### New real data sources (researched and verified live, not assumed)

- **Weather/catastrophic storms**: [GDACS](https://www.gdacs.org/) (Global Disaster Alert and Coordination System) — confirmed real, free, a UN/European Commission cooperation framework, providing a live GeoJSON endpoint for active disasters including tropical cyclones, no API key required. This is a better fit than a generic weather API for "pins used to pin point catastrophic storms" specifically, since it's purpose-built for exactly that. [Open-Meteo](https://open-meteo.com/) (confirmed free, open-source, no-key) as the source for ambient/general weather conditions if the mode needs more than just storm pins.
- **Country demographics**: [REST Countries](https://restcountries.com/) — confirmed real, free, no-key API with population, area, capital, region, currencies, languages, timezones, borders, flags, updated hourly against 35+ sources.
- **Country trade/production**: WorldBank API (already integrated in the old app, real GDP/trade-as-%-GDP indicators) for macro trade figures; [OEC (Observatory of Economic Complexity)](https://oec.world/en/resources/api) for real top-export-by-commodity data ("what they produce the most of") — confirmed it has free unauthenticated access to country trade profile data, though heavier/bulk access needs a free registered tier; verify exact free-tier limits at implementation time and fall back to WorldBank's broader figures if OEC's free access proves too narrow for this app's real usage pattern.
- **Timezone boundaries**: a real, static IANA timezone boundary dataset (e.g. the [timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder) project's GeoJSON, built from real OpenStreetMap data, MIT/ODbL licensed) — downloaded once and bundled/served statically, not a live API dependency, since timezone boundaries don't change often enough to need live fetching. **Current time per zone is computed entirely client-side** via the browser's native `Intl.DateTimeFormat`/`Date` APIs against the real IANA zone name — no API call needed at all, zero rate-limit risk, always accurate.
- **Media embeds**: Wikipedia/Wikimedia's REST API (already partially used in the old app for bilateral-relations lookups) for real country lead images; extend the existing `fetch_real_page_metadata()` (already scrapes `<title>`/meta description from a crisis's real `source_url`) to also capture `og:image`/`og:video` meta tags, so event media comes directly from the real source article rather than being separately sourced or guessed.

### No-fabrication discipline, extended to the new country-analysis feature

"Unique geographical and infrastructural features" and "contribution to the rest of the world" are qualitative asks with no single structured API — the honest approach (matching this session's established AI-primary/static-fallback pattern from the old app's briefing generation) is: when an AI key is configured, generate this text from a prompt that's fed the *real* fetched facts (population, area, GDP, top exports, trade-as-%-GDP) and instructed to describe only what's grounded in that real data, never invent statistics; when no AI key is configured, fall back to presenting the real structured facts plainly (population: X, area: Y km², top exports: Z) without a generated narrative, rather than a fabricated-sounding paragraph. This is the same principle this session enforced repeatedly for the crisis-briefing feature, applied to the new country-analysis feature from day one instead of being retrofitted later.

## UI/UX Design

- **Two sidebars**, `Events` (left) and `Analysis` (right), translucent (semi-transparent background over the globe/starfield, consistent with the old app's existing `.pane`/blur-backdrop CSS pattern — real, reusable visual language, not a new design system).
- **Hover-zone auto-open**: track cursor X position; entering the left 10% of viewport width opens Events, entering the right 10% opens Analysis, moving away closes it (with a short debounce/grace period so briefly crossing the zone or moving toward a sidebar's own content doesn't flicker it shut). A pin/country click force-opens Analysis regardless of cursor position (overriding the hover rule until the user moves the cursor away), since the click itself is the open-intent.
- **Slide transition**: CSS transform-based slide-in/out (translateX), matching the "slides open" wording directly — not a fade or instant toggle.
- **Analysis content branches on what was clicked**: an event pin populates the extensive event-analysis view (title, severity, real source citation, generated/fallback analysis text, embedded media); a country click populates the country-profile view (demographics, geography/infrastructure text, trade routes, top exports, world-contribution figures, embedded media) — two distinct content components sharing the same sliding panel shell.
- **Mode switcher** (Events / Weather / Time Zone) as a small persistent control (e.g. near the logo or the globe's own control cluster) — switching modes changes what's rendered on the globe (crisis pins vs. storm pins + weather overlay vs. timezone boundary lines + live local-time labels) without closing either sidebar or losing the current Analysis selection.
- **Solar-system background**: a separate canvas/WebGL layer behind the MapLibre globe canvas — not tied to real astronomical data (this is decorative, not part of the no-fabrication discipline, which only governs *informational* content) — sparse starfield, a few simple orbiting bodies for visual interest, occasional shooting-star streaks, and occasional UFO sprites/3D models on a random timer, all cheap/low-frequency so it never competes with the real map rendering for GPU budget.
- **Logo**: fixed position at the top of the viewport, above/independent of both sidebars and the mode switcher.

## Target Structure

**Frontend** (`/frontend`, Vite root):
```
frontend/src/
  main.tsx, App.tsx
  api/client.ts, api/types.ts, api/endpoints/{crises,countries,weather,timezones}.ts
  globe/
    Globe.tsx                  — MapLibre instance + globe projection setup
    EventPins.tsx, StormPins.tsx, TimezoneLayer.tsx   — per-mode overlay layers
    ModeSwitcher.tsx
  background/
    SolarSystem.tsx, ShootingStars.tsx, Ufo.tsx        — decorative canvas layer, behind the globe
  sidebars/
    EventsSidebar.tsx, AnalysisSidebar.tsx
    analysis/EventAnalysis.tsx, CountryAnalysis.tsx     — two content views, one sliding shell
    useHoverZone.ts                                     — cursor-position-to-open-sidebar hook
  state/uiStore.ts (active mode, open sidebar, selection), state/queries/*.ts
  styles/*.module.css
  Logo.tsx
```

**Backend** (`/backend`):
```
backend/
  app.py                       — Flask app factory + blueprint registration
  blueprints/{crises,countries,weather,timezones,health}.py
  schemas/{crisis,country,weather}.py                  — Pydantic, replaces to_dict()
  services/
    escalation.py                                      — ported from old app, Goldstein-derived severity
    country_profile.py                                  — new: assembles real facts + AI/fallback narrative, per the no-fabrication rule above
  data_sources/
    gdelt.py, acled.py, newsapi.py, worldbank.py, geocoding.py   — ported verbatim with existing tests
    rest_countries.py, oec.py, gdacs.py                  — new connectors
    timezones.py                                         — serves the bundled static boundary GeoJSON
  models.py                    — extend with any new fields the country-profile/weather features need (real migration, not a rewrite of existing tables)
  tests/                        — Phase 21-23's GDELT filter tests carried over verbatim, plus new tests for the new connectors
  migrations/                   — Alembic, unchanged pattern
```

## Phased Build Order

1. **Backend foundation + data layer port.** Blueprint extraction, GDELT/ACLED/NewsAPI/WorldBank/Nominatim connector port with every Phase 21-23 filter and its test carried over and re-verified before the old file is deleted.
2. **Globe core**: MapLibre GL JS globe projection + OpenFreeMap tiles, standalone, rendering real crisis pins from the ported backend — retires the biggest new technical risk (the globe technology swap) early, before any UI chrome is built around it.
3. **Sidebars shell + hover-zone interaction**, wired to real crisis-pin clicks populating a basic Event Analysis view (title/severity/source) — proves the slide/hover mechanic against real data before the richer country-analysis content is built.
4. **Country click + Country Analysis**: new `countries` blueprint (REST Countries + WorldBank + OEC), `country_profile` service (real facts + AI/honest-fallback narrative), wired into the same Analysis shell.
5. **Weather mode**: GDACS storm pins + Open-Meteo ambient layer, `weather` blueprint, `ModeSwitcher`.
6. **Time Zone mode**: bundled boundary GeoJSON, `TimezoneLayer`, client-side current-time computation.
7. **Media embeds**: Wikipedia/Wikimedia images for country profiles, `og:image`/`og:video` extraction added to `fetch_real_page_metadata()` for event analysis.
8. **Decorative layer**: solar-system background, shooting stars, UFOs — built last since it's purely additive polish with no data dependency, and shouldn't block any functional milestone above.
9. **Logo, cutover + cleanup**: flip Flask static-serving to the new build, delete old `app.js`/`app.css`/`webgl-globe.js`/inline `index.html` script, update `railway.json`/`vercel.json`/`nixpacks.toml`.

## Verification

- After step 1: re-run the ported GDELT/data-source test suite (currently ~196 backend tests) against new module locations — zero regressions before deleting `data_sources.py`.
- After step 2: load the new frontend standalone, confirm the globe renders with real OpenFreeMap tiles in globe projection, real crisis pins appear at correct real coordinates, rotate/zoom/pan work, no console errors.
- After step 3: click a real pin, confirm Analysis slides open from the right with real event data; move the cursor to the left/right 10% zones, confirm Events/Analysis open and close correctly without flicker.
- After step 4: click a real country, confirm Analysis shows real REST-Countries/WorldBank/OEC-sourced facts, and — with no AI key configured (this dev environment's actual state) — confirm the fallback shows real structured facts, not a fabricated-sounding narrative.
- After step 5-6: switch modes, confirm Weather shows real GDACS storm pins (spot-check against GDACS's own live site for a currently-active real storm) and Time Zone shows real boundary lines with correct live local times (spot-check 2-3 zones against real wall-clock time).
- After step 7: confirm at least one real event and one real country show real embedded media, not a broken/placeholder image.
- Throughout: `read_console_messages({onlyErrors:true})` after each interactive step; confirm the no-fabrication discipline holds under direct inspection (no invented numbers anywhere in the new country-analysis or weather features).

## Steps 1-7: ✅ IMPLEMENTED (steps 8-9 remaining)

All independently re-verified live (not just taken on the delegated agents' word) after each step: backend blueprint/data-layer restructuring (207 backend tests passing by step 7), a real MapLibre globe (OpenFreeMap vector tiles, globe projection), dual Events/Analysis sidebars with hover-zone open/close and click-to-pin, real country-click analysis (honest WorldBank fallback since REST Countries now requires a paid key, honest OEC-unavailable messaging since its free tier returns no usable commodity data), Weather mode (real live GDACS storm data), Time Zone mode (real IANA boundary polygons + client-side `Intl`-computed local time, cross-checked correct to the second against real UTC), and real media embeds (Wikipedia country images, event source-article `og:image` extraction).

**One real bug found and fixed during step 7's independent verification** (not caught by the delegated agent, who noted it but attributed it to an out-of-scope "hit-testing quirk"): clicking a crisis pin was silently opening the *country* Analysis view instead of the event one. Root cause: `Globe.tsx`'s marker click handlers never called `stopPropagation()`, so the click bubbled to the map's own country-hit-test layer click handler (MapLibre's layer-click system listens via the container, not just the canvas), which fired second and overwrote the event selection. Fixed by adding `e.stopPropagation()` to both the crisis-marker and storm-marker click handlers in `frontend/src/globe/Globe.tsx`. Re-verified live: a real crisis pin click now correctly opens the event Analysis view (confirmed with real data and a real embedded image from the source article in the same test).

## Step 9: ✅ IMPLEMENTED — logo, production cutover, and two real production-only bugs found and fixed

Logo ("🌐 GeoIntel", matching the app's real existing name), old pre-rewrite frontend files deleted (`app.js`, `app.css`, `webgl-globe.js`, `index.html`, `frontend-api.js`, `api-docs.html`, old static assets), `backend/app.py`'s static-serving routes repointed at `frontend/dist/`, deploy configs (`nixpacks.toml`/`vercel.json`) updated for the new build step. The delegated agent's own run was interrupted mid-verification by a session rate limit (had only gotten as far as "map is rendering correctly... proceed with full interaction testing"), so the actual production path — loading `http://localhost:5000/` for the first time ever, rather than the Vite dev server — had never been fully verified when I picked this up. It was not actually working:

1. **MapLibre's worker script was silently broken in production** — a washed-out white globe with zero crisis pins rendered. Root cause: MapLibre GL's worker file (`maplibre-gl-worker.mjs`) does a plain ES `import` from its own sibling `maplibre-gl-shared.mjs` inside the published npm package; Vite's automatic worker-chunking (triggered by MapLibre's internal `new Worker(new URL(...))` call) emitted the worker chunk but never followed that further nested import, so the production build shipped a worker file whose own dependency 404'd — Flask's SPA-style fallback then served `index.html` for that 404, which the browser correctly rejected as "not a JS module." This is a known MapLibre+Vite integration issue. Fixed by copying MapLibre's real, unmodified `maplibre-gl-worker.mjs` and `maplibre-gl-shared.mjs` straight from `node_modules/maplibre-gl/dist/` into `frontend/public/` (served as plain static files, bypassing Vite's fragile auto-bundling for this library) and calling `maplibregl.setWorkerUrl('/maplibre-gl-worker.mjs')` before map construction in `Globe.tsx`.
2. **CSP silently broke every country click in production** — `backend/app.py`'s `_CSP` header's `connect-src` allowed `tiles.openfreemap.org`/Wikipedia/Supabase but not `cdn.jsdelivr.net`, which is exactly where `Globe.tsx`'s invisible country-hit-test layer fetches its real Natural Earth country-boundary GeoJSON from client-side. The fetch was silently blocked with no functional symptom beyond a CSP violation in the console — country clicks just did nothing. Fixed by adding `https://cdn.jsdelivr.net` to `connect-src`.

Both confirmed fixed and re-verified live end-to-end through the real production path (`http://localhost:5000/`, not the dev server): logo, real globe with real tiles and real crisis pins, real event-pin clicks (real briefing text + real embedded image), real country clicks (real Brazil demographics/flag), Weather mode (real storm pins) and Time Zone mode (real boundary lines) both confirmed to preserve the Analysis selection across mode switches, exactly as required. Backend: 207/207 tests passing. `git status` confirmed clean — old files removed, new structure in place, `node_modules`/`dist` properly gitignored, no stray artifacts.

**The rewrite (all 9 steps) is complete.**

---

# Phase 10: Post-rewrite refinements — sidebar UX, event categories, local/global scope, camera fly-to, draw/measure tool

## Context

Direct hands-on testing of the rewritten app surfaced six real gaps. Two of them (the hover-close rule and the edge-tab affordance) needed a clarifying decision since they touch behavior built and verified earlier in the rewrite (the "pinned Analysis stays open" mechanic from step 3) — resolved directly with you: hovering the globe now **always** closes both sidebars, replacing the sticky-pin behavior entirely; and the invisible 10%-of-screen hover zones become **visible edge tab handles**. The "Local/Global" toggle turned out not to be about geography at all — "Local" means small-scale, non-geopolitical content (city/town crime, accidents, human-interest stories), which is exactly the class of noise this session's GDELT filtering work (Phases 21-23 of the original app, ported verbatim into `backend/data_sources/gdelt.py` during the rewrite) was built to *reject* at ingestion. Supporting a real "Local" mode means turning some of those reject-filters into a *classification* instead of a *deletion* — reusing the exact same hard-won signals, not building new ones.

## 10.1 — Events sidebar: All / Major / Categories tabs

Add a small tab row to the top of `frontend/src/sidebars/EventsSidebar.tsx`, above the crisis list:
- **All**: no filter (current behavior).
- **Major**: filter to `severity >= 70` (a real, already-present field — no backend change).
- **Categories**: reveals a row of filter chips built from the real `type` values already in the data (`conflict`, `diplomatic`, `civil_unrest`, `military`, etc. — the same set `CRISIS_TYPES` already names in `backend/data_sources/constants.py`) — clicking a chip filters the list to that type, clicking again clears it.
Implement as client-side filtering in `EventsSidebar.tsx` (or a small `filters` slice in `uiStore.ts` if other components need to read the active filter) — the full crisis list is already fetched client-side via `useCrisesQuery()`, so this is a pure array filter, no new endpoint.

## 10.2 — Hover-driven sidebar visibility, replacing the sticky-pin mechanic

Rework `frontend/src/sidebars/useHoverZone.ts` and `frontend/src/state/uiStore.ts`:
- Remove the step-3 "pinned selection keeps Analysis open regardless of cursor" behavior entirely (confirmed with you this is being replaced, not layered on top of).
- Split state into **selection** (what content to show — set by clicking a pin/country, persists until a new one is clicked) and **visibility** (purely hover-driven — is no longer tied to selection at all).
- Visibility rule: hovering the left edge tab (10.3) opens Events; hovering the right edge tab or the open Analysis panel's own content opens/keeps-open Analysis; hovering anywhere on the globe/map canvas itself force-closes both, unconditionally, overriding whatever else is happening. A click on a pin/country still updates the *selection* (so Analysis shows the right content next time it's opened) but no longer force-opens or pins the panel open by itself — per your explicit choice, moving the cursor onto the globe right after clicking will close it again.

## 10.3 — Visible edge tab handles

Replace the invisible 10%-of-viewport hover-zone detection with small, always-visible pull-tab elements fixed to the left and right screen edges (e.g. a narrow rounded rectangle with a chevron, similar visual language to the existing translucent sidebar/mode-switcher styling) — `frontend/src/sidebars/EdgeTab.tsx`, one instance per side. These are the real hover targets `useHoverZone.ts` now listens on (via `mouseenter`/`mouseleave` on the tab elements themselves, same "panel-hover fusion" pattern already used for keeping a sidebar open while the cursor is over its own content) — a plain click on the tab also toggles it open, for accessibility/discoverability beyond pure hover.

## 10.4 — Local/Global news scope

**Backend**: add a real `scope` column to `Crisis` (`'global' | 'local'`, migration required). In `backend/data_sources/gdelt.py`'s `_parse_row()`, change the existing self-referential/generic-actor-name/blank-actor-violent-root/demonym checks from `return None` (reject) to setting `scope = 'local'` on the parsed row instead of discarding it — these signals were already verified, live, across multiple phases this session to reliably indicate exactly this class of content (routine local crime/accident/human-interest stories GDELT's CAMEO parser mis-tags as conflict). Rows that pass all filters cleanly get `scope = 'global'`. The existing fan-out/dedup caps (`_cap_fanout_per_source_url`, `_cap_fanout_per_event_cluster`, `_cap_fanout_per_title_day`) still apply to both scopes (still real duplicate/syndication problems either way). Add `scope` to `blueprints/crises.py`'s response shape and as a query-string filter on `GET /api/crises` (`?scope=global|local|all`).

**A real, necessary side effect to flag**: this session already proved GDELT's Goldstein-derived severity is unreliable specifically for this class of content (a "school fights student" story reliably shows severity 100). Local-scope rows should not be displayed with the same "Critical severity" framing as global ones — the frontend's `Major` filter (10.1) and any severity badge styling should either suppress/mute severity for `scope='local'` rows or caveat it, rather than presenting an already-known-unreliable number at face value. This is a UI-honesty detail worth getting right, not a blocker for shipping the toggle.

**Frontend**: a two-state toggle (Local/Global) near the Events tab row from 10.1, filtering the list via the new `scope` query param; also apply to the globe's own pin rendering in Events mode (`Globe.tsx`) so the pins on the sphere match what's in the list.

## 10.5 — Click event flies the camera to its pin

In the crisis-list click handler (`EventsSidebar.tsx`) and the marker click handler (`Globe.tsx`), call `map.flyTo({ center: [crisis.lon, crisis.lat], zoom: <a real, tuned "front and center" zoom level — start around 4-5 and adjust live>, essential: true })` — MapLibre's real, already-relevant API (the same library already in use throughout the rewrite), no new dependency. Keep the existing `selectCrisis()` call alongside it — flying the camera and opening Analysis both happen from the same click.

## 10.6 — Draw & measure tool

Add [`maplibre-gl-terradraw`](https://github.com/watergis/maplibre-gl-terradraw) (a real, actively-maintained MapLibre GL JS plugin built on `terra-draw` + Turf.js) — confirmed it ships point/line/polygon/rectangle/circle/freehand drawing modes out of the box, with Turf providing real geodesic distance/area/centroid math, covering all three things you asked for (distance measurement, area measurement, freehand drawing) in one well-supported package rather than three custom implementations. Add a new toggle button near the existing globe controls (`ModeSwitcher`'s cluster, or its own small icon button) that activates/deactivates the draw toolbar; wire its real measurement output (Turf-computed distance in km/mi, area in km²) into a small on-screen label near the drawn feature, matching this app's established "always show the real computed number, never a placeholder" convention.

## 10.7 — Clean up the event Analysis text: stop repeating what's already shown elsewhere in the panel

Confirmed live: the static-fallback analysis text currently opens with something like *"Seoul criticizes Ukrainian (North Korea) is rated **Low** at severity 20/100[1], holding at current intensity. GDELT-monitored event (CAMEO 112), reported via {source_url} Primary source description..."* — this repeats the severity (already shown in the badge above) and the source URL (already shown in the dedicated SOURCE section above) inside the prose itself, and reads awkwardly. And the text currently ends with an appended `## Sources` section listing the exact same single `source_url` a second time. Fix both in `backend/services/briefing.py`'s static-fallback generator:
- Replace the current opening sentence with a plain, minimal lead-in: `Global Severity: {severity}/100` on its own line, then go straight into the real analysis content (the actual GDELT CAMEO-derived description/context) — no restating of the actor/verb/source-URL sentence that's already redundant with the badge and SOURCE section.
- Remove the appended `## Sources` section entirely from this static-fallback path — the one real citable source is already surfaced in `EventAnalysis.tsx`'s dedicated SOURCE block above the analysis text, so repeating it below is pure duplication, not a second real source. Leave the underlying `crisis.source_url` plumbing untouched (still feeds the SOURCE section) — this is a text-formatting change only, not a data change.

## 10.8 — Background: constellations instead of planets

In `frontend/src/background/SolarSystem.tsx`: remove the 5 drifting planet circles (the gradient-shaded/ringed decorative bodies added in step 8) and add a handful of constellation-like groupings — simple faint line segments connecting a few nearby stars from the existing 90-star field, per the original ask (a look this rewrite's step 8 didn't quite land on, having built planets instead). Keep the starfield twinkle, shooting stars, and UFOs exactly as they are — only the planets are being removed/replaced.

## 10.9 — Hide crisis pins on the far side of the globe

Confirmed: MapLibre `Marker`s are plain screen-projected DOM elements, not real 3D-occluded objects — on a globe projection, a marker whose real lat/lon is on the far hemisphere (behind the sphere from the camera's current viewing angle) still renders on top of the globe's own (correctly-occluded) surface, as if the globe were transparent. Fix in `frontend/src/globe/Globe.tsx`'s marker-rendering/update logic: for each marker, compute whether its coordinate is on the near or far hemisphere relative to the map's current center (a real spherical-geometry check — the angular/great-circle distance between the marker's lng/lat and the map's current center point; beyond ~90° it's on the far side) and toggle that marker's visibility (`display: none` on its element, or remove/re-add) accordingly. Recompute on every camera move (`map.on('move', ...)`), not just once, since which hemisphere is "near" changes continuously as the globe rotates/pans. Apply this to crisis pins, storm pins, and any other marker type added later — a small shared helper (e.g. `isOnNearHemisphere(map, lng, lat)`) rather than duplicated logic per marker type.

## Verification

- 10.1: confirm All/Major/Categories filters against the real live crisis list — Major should visibly shrink the list to only severity ≥70 items; a Category chip should show only that real type.
- 10.2/10.3: hover each edge tab, confirm the correct sidebar opens; move onto the globe, confirm both close immediately regardless of prior click state; click a pin, then move onto the globe, confirm Analysis closes (per the explicit design choice), then hover the right edge tab again and confirm the same crisis's data is still there (selection persisted even though visibility didn't).
- 10.4: after the migration, spot-check real live GDELT rows — confirm a known noisy pattern (e.g. "School fights Student") now lands as `scope='local'` instead of being silently dropped, and a real geopolitical story stays `scope='global'`; confirm the toggle actually changes both the list and the globe's pins; confirm local-scope items don't show an unqualified "Critical" badge.
- 10.5: click several crisis pins/list items, confirm the camera genuinely flies to and centers each one at a sensible zoom, not just teleporting or overshooting.
- 10.6: draw a line between two real, distant cities, confirm the displayed distance is a real, correct great-circle figure (spot-check against a known real distance); draw a polygon, confirm a real area figure displays; confirm freehand drawing works and doesn't crash the map.
- 10.7: click a real event pin, confirm the analysis text now leads with a plain `Global Severity: xxx/100` line (no restated actor/verb/source sentence) and confirm no `## Sources` block appears at the bottom, while the SOURCE section above the analysis still shows the real link.
- 10.8: confirm the decorative background shows real constellation line-groupings among the stars, no planet circles remain, and shooting stars/UFOs still fire as before.
- 10.9: rotate the globe with several crisis pins near the visible limb, confirm pins smoothly disappear as they rotate onto the far side and reappear as they rotate back into view, with no pins visibly floating on top of the globe's own far-side surface.
- Full regression: re-run the backend test suite after the `scope` migration; reload the production path (`http://localhost:5000/`) and confirm nothing from steps 1-9 (event/country clicks, media embeds, Weather/Time Zone modes) broke.

## Phase 10: ✅ IMPLEMENTED — all 9 items, plus two real gaps found and fixed during independent verification

All five workstreams (backend scope+text, sidebar/hover/tabs, globe fly-to+hemisphere, background constellations, draw/measure) were dispatched in parallel and independently re-verified live, not taken on the delegated agents' word. 218/218 backend tests passing, frontend build clean.

**Two real gaps found and fixed during verification, beyond what the delegated agents reported:**

1. **10.7's briefing-text cleanup was incomplete.** The delegated agent removed the old opening sentence and the `## Sources` block correctly, but `crisis.analysis` — which for every GDELT row is the fixed ingestion template `"GDELT-monitored event (CAMEO nnn), reported via {source_url}"` — was still being echoed verbatim into the "real analytical content" portion of the text, along with a now-dangling `[1]` citation marker pointing at a Sources list that no longer existed. Both were exactly what you'd originally quoted as wanting gone. Fixed in `backend/services/briefing.py`: strip the GDELT boilerplate clause via regex before including `crisis.analysis` (preserving any *other* real, non-boilerplate analysis text for non-GDELT sources), and dropped the bracket-citation phrasing from the static path's corroboration sentence. Also found and fixed a real test-isolation bug while fixing the tests for this: `test_briefing.py`'s tests all reused crisis id `'brief-1'`, and `generate_ai_briefing` caches its result by that id — without clearing the cache between tests, a later test could silently be served an earlier test's stale cached result. Re-verified live against a real GDELT crisis: output is now exactly `Global Severity: 100/100`, real trend/economic/reliability content, no restated metadata, no dangling citation, no Sources block.
2. **A browser-automation testing-tool limitation, not a real app bug**: the `hover` action used for live verification doesn't always fire a real `pointerover` event the app's globe-hover-closes-sidebars listener depends on, making the feature look broken in testing. Confirmed the app's own logic is correct by dispatching a genuine `pointerover` event directly — the sidebars closed exactly as designed. No code change needed; noted for future verification passes in this session.

All other items (10.1 tabs, 10.3 edge tabs, 10.4 local/global scope — confirmed live via a real GDELT fetch producing 515 global/86 local rows, with real examples like "United States fights United States" and "Judge criticizes Florida" landing correctly as local — 10.5 fly-to, 10.6 draw/measure with real Turf-computed distances, 10.8 constellations, 10.9 hemisphere culling with real spherical-geometry math confirmed correct at the poles and antimeridian) matched their agents' reports under independent re-verification with no further issues found.

---

# Phase 11: Resolve real event titles at sync time, not on read

## Context

Every GDELT-sourced crisis in the rewritten app shows a generic, auto-generated title forever (a CAMEO-verb construction like `"Seoul criticizes Ukraine"`, or the blank-actor fallback `"Conflict-related event in {country}"`) — never the real article headline. Investigating why: the backend already has a real, working, tested endpoint for this (`GET /api/crises/<id>/real-headline`, calling the real `fetch_real_page_metadata()` utility against the crisis's actual `source_url`) — it's just **completely unwired on the new frontend**. Nothing in the rewrite calls it. The old (pre-rewrite) app resolved this lazily on click plus an eager, rate-limited prefetch for the visible list; confirmed directly with you that this rewrite should NOT repeat that pattern — instead, **resolve the real title once, at sync time, and store it directly as `crisis.title`**, so by the time any frontend ever reads a crisis, its title is already real. No generic-then-real flash, no per-view network dependency, no lazy-fetch UX complexity at all.

**The real engineering tradeoff this introduces** (the actual reason the old app avoided doing this eagerly): a single sync run's GDELT step alone produced ~530 new surviving rows in the sync just run this session — resolving each one's real title means a real HTTP GET to an arbitrary external news site per row. Serially, at up to 8s/request (the existing real timeout in `fetch_real_page_metadata()`), that's a worst-case sync duration in the tens of minutes. The fix is bounded concurrency (a thread pool), not skipping the work.

## 11.1 — Resolve titles only for rows that survive dedup, not every raw parsed row

In `backend/data_sources/gdelt.py`'s `GDELTConnector.fetch_recent_events()`: keep the existing order (`_parse_row()` for every raw TSV line → `_cap_fanout_per_source_url` → `_cap_fanout_per_event_cluster` → `_cap_fanout_per_title_day`) exactly as-is, since these are cheap, no-network operations that already discard a large fraction of raw rows (permutation explosions, syndicated duplicates). **Add real title resolution as a new step AFTER all three caps**, operating only on the survivors — resolving a title for a row that's about to be dropped as a duplicate would be pure wasted network traffic.

## 11.2 — Bounded-concurrency real title resolution

New function `GDELTConnector._resolve_real_titles(crises)` in the same file: for each surviving crisis dict, call the existing `fetch_real_page_metadata(crisis['source_url'])` (already real, already does the right cleanup via `_clean_article_title()`) — but run these concurrently via `concurrent.futures.ThreadPoolExecutor` (a bounded pool, start at 8-10 workers and tune live against real sync timing) rather than serially, since these are independent I/O-bound HTTP calls with no shared state. For each row: if a real, non-empty cleaned title comes back, replace `crisis['title']` with it; if the fetch fails, times out, or `_clean_article_title()` rejects what came back (e.g. a date-only title), **keep the existing generic auto-generated title as the honest fallback** — never blank, never fabricated, exactly the same "AI/fetch-primary, honest-static-fallback" principle already used everywhere else in this codebase.

## 11.3 — Wire it into `fetch_recent_events()`

One new line after the existing three caps: `crises = GDELTConnector._resolve_real_titles(crises)`. No other call sites change — `DataAggregator.sync_all_sources()` already calls `fetch_recent_events()` and upserts whatever it returns, so once `title` is correct in the returned dicts, it's correct everywhere downstream (Events list, Analysis panel heading, globe pin popups) with zero frontend changes needed.

## 11.4 — The existing lazy `real-headline` endpoint stays, scoped to location refinement only

`GET /api/crises/<id>/real-headline` also does real AI-extraction + Nominatim location refinement for GDELT rows (a heavier, AI-involving operation this plan is explicitly NOT moving to bulk ingestion time — that stays a deliberate, lazy, on-click operation, unrelated to titles). Its title-resolving half becomes redundant once 11.1-11.3 ship (since `crisis.title` will already be real by then) but is harmless to leave as dead-weight — not a cleanup priority for this phase.

## Verification

- Run `GDELTConnector.fetch_recent_events()` directly against the live feed, before/after timing it — confirm real titles now come back for rows with a resolvable article (spot-check several against the real page), confirm rows with an unresolvable/failed fetch still show their honest generic fallback (not blank, not broken), and confirm the added wall-clock time is reasonable for an hourly sync (tune the thread-pool size live if it's not).
- Run a real full sync (`DataAggregator.sync_all_sources()`, the same one just run this session) and confirm via a live `GET /api/crises` call that newly-ingested GDELT rows have real headline-style titles, not CAMEO-verb constructions, while a control check confirms local-scope classification (Phase 10.4) and the fan-out caps still behave exactly as before (this change sits after them, shouldn't affect what survives).
- Load the real app and confirm the Events list and Analysis panel heading both show real titles immediately on load/click, with no flash of generic text and no extra network request from the frontend.
- Re-run the backend test suite; add tests for `_resolve_real_titles()` (mocked HTTP, covering: successful resolution replaces the title, a failed/timed-out fetch keeps the generic fallback, a rejected/date-only title keeps the generic fallback) and confirm the existing `_cap_fanout_*`/`_parse_row` tests are unaffected by the new step being inserted after them.

## Phase 11: ✅ IMPLEMENTED and verified live

`GDELTConnector._resolve_real_titles()` added to `backend/data_sources/gdelt.py`, wired into `fetch_recent_events()` right after the three existing fan-out caps (so it only ever runs against dedup survivors), using a bounded 8-worker `ThreadPoolExecutor` against the existing `fetch_real_page_metadata()`. 8 new tests, `test_gdelt.py` 105/105, backend-wide 225/225 (up from 218).

**Live verification, real data, no mocks**: ran the connector directly against the live GDELT feed — 557 real rows in 107.4s (a reasonable per-sync cost), **525 of 557 (94%) resolved to genuinely real article headlines** (e.g. *"UN extends Haiti's Gang Suppression Force mandate to March 2027 amid rising violence"*, *"Two Orbán-Era Ministers Detained in Hungary as Critics Question Magyar's Methods"*), with the remaining 6% falling back honestly to their generic auto-generated title after a real, logged fetch failure (403s from sites blocking bots, DNS failures, timeouts — all expected real-world outcomes, never blanked or fabricated). Ran a real full sync afterward; a direct query of the 600 most-recently-inserted GDELT rows in the live database confirmed 524/600 (87%) now carry real headlines.

**One real, worth-flagging limitation, in scope as approved**: this only resolves titles for *newly-ingested* rows going forward — the ~7,864 rows already in the database before this shipped were not retroactively backfilled (not part of the approved scope, which was specifically "at sync time"). The live Events list, when sorted by severity, still surfaces old pre-existing generic/legacy-titled rows at the top (severity-100 items dominate that sort, and old rows are disproportionately represented there) — the fix is confirmed genuinely working for all new data, it just doesn't retroactively rewrite history. A follow-up retroactive backfill (the same pattern as `cleanup_duplicate_crises.py` — query existing generic-titled rows, run them through `_resolve_real_titles()`, update in place) would be a natural, small next step if wanted.

---

# Phase 12: Premium foundation (accounts, entitlements, locked-feature UX)

## Context

The app is free and anonymous today. The product owner wants it to stay usable without signing up, with a set of new **premium** features behind a membership: user network (follow, comments tab, groups, chat), user dashboard (alert locations, source filters, saved items, curated feed, messages, groups), branch scenarios, topography/satellite layers, and user-submitted pins (a "User" tab beside Global/Local). Decisions already made: user data lives in **Supabase** (same project as asix.live); free users can *read* comments but not post; premium features are shown **locked** (not hidden) with an upgrade prompt; moderation = report + auto-hide tools; sign-in = **redirect to the asix.live login**. This phase builds only the shared foundation every premium feature depends on; no premium feature ships here.

Facts established from the repo / owner:
- `backend/services/auth.py` already verifies Supabase JWTs (HS256, `SUPABASE_JWT_SECRET`) but only for admin routes (`check_admin_key`, used in `blueprints/crises.py` and `blueprints/health.py`). PyJWT is already in `requirements.txt`.
- Supabase `subscriptions` table (written by the existing asix.live Stripe webhook): `id, user_id, project_id, stripe_customer_id, stripe_subscription_id, plan, status, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at`. `project_id` is per-app, so GeoIntel must filter on its own project id.
- Frontend (`frontend/src/api/client.ts`) uses bare `fetch` with `VITE_API_BASE_URL`; Vercel proxies `/api/*` to Railway, so browser calls are same-origin in production.
- The asix.live site currently redirects non-subscribers to login in front of the apps; that gate must stop applying to GeoIntel (outside this repo — owner action).

## Work split (decided)

This repo/chat builds everything GeoIntel-side (12.1–12.4). The asix.live-connected chat owns: removing the login redirect for GeoIntel, the session handoff back to `geointel.asix.live`, confirming GeoIntel's `project_id` and the Stripe webhook's `status` values, the upgrade/pricing URL, and applying the Supabase SQL files. A handoff brief for that chat is written alongside this plan (see the chat reply); both sides work from that contract.

## 12.1 Backend: user identity + entitlements

- `backend/services/auth.py`: add `get_current_user()` (verifies the Bearer JWT, returns `{id: sub, email}` or `None`) by factoring the existing decode out of `check_admin_key` (which keeps working unchanged and is reused for admin). Support the legacy HS256 `SUPABASE_JWT_SECRET` and, when the token header says ES256/RS256, verify via Supabase's JWKS (`SUPABASE_URL` + `/auth/v1/.well-known/jwks.json`, `jwt.PyJWKClient`) — newer Supabase projects use asymmetric keys.
- New `backend/services/entitlements.py`: `get_plan(user_id)` queries Supabase REST (`/rest/v1/subscriptions?user_id=eq.<id>&project_id=eq.<GEOINTEL_PROJECT_ID>`) with the service-role key (server env only), ~60 s in-process TTL cache via the existing `cache.py`. Premium = `status in ('active','trialing')`, or `canceled` with `current_period_end` in the future. Fail closed to free on any lookup error (log it).
- Decorators in `services/auth.py` (or a small `services/gating.py`): `optional_user` (attaches `g.user`/`g.plan`; anonymous allowed) and `require_premium` (401 anonymous, 403 signed-in-but-free, JSON body says which so the UI can show "sign in" vs "upgrade").
- New `backend/blueprints/me.py`: `GET /api/me` → `{signedIn, userId?, plan: 'free'|'premium', premium: bool}`; registered in `app.py` beside the other blueprints. Rate-limited with the existing Flask-Limiter setup.
- New env vars (Railway, owner sets; never committed): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEOINTEL_PROJECT_ID`; existing `SUPABASE_JWT_SECRET` kept for HS256.

## 12.2 Supabase schema (SQL files in repo, applied by the owner)

- `backend/supabase/001_profiles.sql`: `profiles(user_id pk → auth.users, display_name, avatar_url, created_at)` with RLS (anyone can read public fields; a user can only insert/update their own row). Social/dashboard/pin tables are added with their own phases, each shipped as a numbered SQL file; none are created here beyond `profiles`. Nothing is run against the owner's Supabase by me.

## 12.3 Frontend: session, entitlements, locked UX

- Session: a small `frontend/src/auth/session.ts` that reads the Supabase session returned from the asix.live login redirect (shared `.asix.live` cookie if available, else token handed back on the redirect URL and stored in memory/localStorage), exposes `getAccessToken()`, `signIn()` (redirect to asix.live login with a return URL), `signOut()`. Exact handoff mechanism depends on how asix.live stores its session — confirm with the owner/asix.live code before writing; fall back to a Supabase JS client in GeoIntel if sharing isn't possible.
- `api/client.ts`: attach `Authorization: Bearer` when a session exists (small `authedFetch` wrapper used by new endpoints; existing public calls untouched).
- `state/queries.ts`: `useEntitlementsQuery()` → `/api/me`; Zustand slice or hook `useEntitlements()` returning `{signedIn, premium}`.
- New `frontend/src/components/PremiumGate.tsx` (+ CSS module): wraps any feature; premium users see children, others see the child dimmed/disabled with a lock badge and a CTA — "Sign in" if anonymous, "Upgrade" (link to the asix.live billing/pricing page) if signed-in free. Add a small account chip (sign in / plan badge) near the Logo or ModeSwitcher.
- Use `PremiumGate` first on one real placeholder (e.g. a disabled "Satellite" toggle in ModeSwitcher's cluster) to prove the path end to end; real premium features land in later phases.

## 12.4 Tests

- `backend/tests/test_entitlements.py`: premium/free/canceled-in-period/expired/lookup-failure (fail closed), project_id filtering, cache hit.
- `backend/tests/test_gating.py`: `/api/me` anonymous / free / premium; a dummy `@require_premium` route returns 401/403/200; expired and tampered JWTs rejected; HS256 and JWKS paths (JWKS mocked). Existing `test_admin_auth.py` must stay green (needs `PyJWT` installed locally).
- Frontend: type-check/build; manual browser verification of locked vs unlocked states with a mocked `/api/me`.

## Verification

1. Backend suite green (`pytest`, incl. new tests; install PyJWT locally to run `test_admin_auth.py`).
2. With `SUPABASE_*` unset locally, `/api/me` returns anonymous/free and the app behaves exactly as today (no regression for free users).
3. With a test JWT + a seeded `subscriptions` row (against a throwaway Supabase project or mocked REST), `/api/me` returns premium and `@require_premium` routes return 200; remove the row → 403.
4. In the browser: locked toggle shows the lock + "Sign in" when anonymous, "Upgrade" when free, and works when premium; verify via the preview tools.
5. Owner-side checklist before production: set the three env vars on Railway; set `GEOINTEL_PROJECT_ID`; remove/skip the asix.live login redirect for GeoIntel; run `001_profiles.sql`.

## Out of scope (later phases, in suggested order)

Satellite/topography layers → dashboard (saved events, source filters, location alerts) → comments tab (free read / premium post), follows, user pins ("User" tab) with report + auto-hide moderation → branch scenarios (AI, per-user limits, labeled AI-generated) → groups and chat (Supabase Realtime) last.

---

# Phase 13: Performance (slow load, slow interaction, mobile browser crashes)

## Context

GeoIntel loads slowly, interacts slowly, and crashes mobile browsers. Measured against production (`geointel.asix.live`), the cause is data volume meeting a render path that doesn't scale:

- `GET /api/crises` returns **32,168 events** (~26 MB raw JSON, **3.1 MB gzipped**, 1.1–2.3 s) because **nothing ever expires events** (no retention logic exists) and the frontend sends no `days`/limit. GDELT adds **~11,000 events/day** (measured: 11,048 in the last 24 h, 31,988 in 3 days), so it only gets worse; 7 days ≈ 77k.
- Each row is 815 B, but the frontend only reads 10 fields (`id,title,country,type,severity,scope,date,lat,lon,source_url`); the rest (domains, analysis boilerplate, stakeholders…) is dead weight.
- `Globe.tsx` `addCrisisMarkers` creates a **DOM `maplibregl.Marker` + `Popup` per event** (32k DOM nodes/objects), and `updateMarkerVisibility` loops all of them (32k `getLngLat` + style writes) on **every `move` event**.
- `EventsSidebar.tsx` renders **every event as a `<button>`** (32k rows, no windowing).
- Single 1.6 MB JS bundle (maplibre + terradraw + app); `DrawMeasureControl`/terradraw is loaded eagerly. `SolarSystem` runs a `requestAnimationFrame` canvas loop at DPR up to 2 continuously, under `backdrop-filter: blur(14px)` panels over a WebGL canvas (expensive on phones).
- No DB index covering the list query (`is_active, scope, date_start`); response uses `Cache-Control` default (Vercel `MISS`), so every visitor pays the full cost after the 60 s in-process cache expires.

Decisions made with the owner: default view = **last 48 h** with a **24h / 48h / 7d range selector** (7d capped at the top 10,000 by severity then recency); events older than 7 days are **archived** (`is_active=False`, rows kept), not deleted. Premium history features can later build on the archived rows.

Goal: first useful render in ~2 s on a mid-range phone, no crashes, smooth pan/zoom, with the same look and behavior.

## 13.1 Backend: bounded, lean, cacheable list

- `backend/blueprints/crises.py` `get_crises`: add `view=map` (lean fields only: `id,title,country,type,severity,scope,date,lat,lon,source_url`, built directly from columns — skip `to_dict()` and the stakeholders/domains work) and `limit` (server max 30,000). With `days` set, sort by `date_start desc` for ≤2 days; for larger windows sort `severity desc, date_start desc` and cap at 10,000. Default behavior with no params stays unchanged (other consumers: export, admin).
- Cache key already includes params; add `view`/`limit`. Response headers `Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=300` so Vercel's edge serves repeat visitors (verify `X-Vercel-Cache: HIT`).
- New `backend/services/retention.py` `archive_old_crises(days=7)`: set `is_active=False` for rows with `date_start` older than the cutoff, **excluding** `source='CURATED'`, `date_scheduled IS NOT NULL`, and `status='upcoming'`. Call it from `scheduled_sync()` in `app.py` after the sync, then `cache_clear_prefix('crises:')`. First hourly run after deploy archives the backlog (batched UPDATE).
- Alembic migration (new file in `backend/migrations/versions/`, after `a1f3c8d9e6b2`): composite index `ix_crises_active_scope_date (is_active, scope, date_start)`.

## 13.2 Frontend: GPU-rendered pins instead of DOM markers

- `frontend/src/globe/Globe.tsx`: replace `addCrisisMarkers`/crisis use of `markersRef` with one clustered GeoJSON source (`cluster: true`, `clusterRadius ~45`, `clusterMaxZoom ~6`) and three layers: cluster circles (color/size by `point_count`), cluster counts (confirm a glyph font the OpenFreeMap style serves), and unclustered points colored by severity using the same thresholds as `colorForSeverity` in `globe/severity.ts` (`['step', ['get','severity'], ...]`). Local-scope points muted as in the list.
- Interaction: cluster click → `getClusterExpansionZoom` + `easeTo`; point click → `selectCrisis` (look up the full summary in a `Map` by id), existing fly-to behavior, and one shared on-demand `Popup` (title/country/severity) replacing 32k per-marker popups; hover cursor via `mouseenter/leave`. Keep the click-vs-country-hit-layer precedence fix (queryRenderedFeatures order) so a pin click never opens the country view.
- Delete `updateMarkerVisibility`/`isOnNearHemisphere` for crises: MapLibre's globe projection already occludes far-side layer features. Keep the DOM-marker + hemisphere path only for storms (a handful of markers).
- Update data via `source.setData` when the query result changes (not remove/re-add).

## 13.3 Frontend: lean data + range selector + virtualized list

- `api/types.ts`: add `CrisisSummary` (the 10 fields); `uiStore.pinnedSelection` and `EventAnalysis` use it (briefing/detail already fetched by id). `api/client.ts` `fetchCrises({scope, days, view:'map'})`; `state/queries.ts` `useCrisesQuery(scope, range)` with `placeholderData: keepPreviousData` so switching range doesn't blank the globe.
- `state/uiStore.ts`: `timeRange: '24h' | '48h' | '7d'` (default `48h`) + setter; map to `days` 1/2/7. Add a compact range selector row in `EventsSidebar.tsx` beside the Global/Local toggle.
- `EventsSidebar.tsx`: window the list with `@tanstack/react-virtual` (same TanStack family already used for `react-query`); fixed row height, ~30 DOM rows regardless of list size; keep tabs/category filters as client-side array filters.

## 13.4 Bundle and device load

- `vite.config.ts`: `manualChunks` for `maplibre-gl`; lazy-load `DrawMeasureControl` (terradraw + its CSS) on first toggle via dynamic `import()`; lazy-load `SolarSystem` after first paint (`React.lazy` + idle). Re-check `dist/assets` sizes before/after.
- `background/SolarSystem.tsx`: pause the rAF loop when `document.hidden`; honor `prefers-reduced-motion`; DPR capped at 1 and drop shooting stars/UFOs on small screens or `navigator.hardwareConcurrency <= 4`.
- CSS: disable `backdrop-filter` on the translucent panels at `max-width: 768px` (solid translucent background instead) — files: `Logo.module.css`, `ModeSwitcher.module.css`, `EdgeTab.module.css`, `AccountChip.module.css`, `EventsSidebar.module.css`, `AnalysisSidebar.module.css`.
- Map options: cap `pixelRatio` at 2 on mobile.

## 13.5 Tests

- `backend/tests/test_crises_list.py` (or extend existing): `view=map` returns only the lean keys; `days` window filters; 7d cap respects `limit`/10,000 and ordering; default (no params) unchanged; `Cache-Control` header present.
- `backend/tests/test_retention.py`: archives old GDELT rows, leaves recent rows, `CURATED`, scheduled (`date_scheduled`) and `upcoming` rows untouched; idempotent.
- Frontend: `tsc -b`, `vite build`; manual checks below.

## Verification

Capture baseline then after, same machine, using the Browser preview tools (`javascript_tool`, `resize_window` mobile preset, `read_network_requests`):
1. Payload: `/api/crises?days=2&view=map` raw and gzipped size and time (target ≤ ~600 KB gz at ~22k rows; was 3.1 MB gz for 32k).
2. DOM: `document.querySelectorAll('*').length` after load with the Events panel open (target: low thousands; baseline to be measured first, expected on the order of 100k with ~32k pins + ~32k list rows), and list DOM rows (~30).
3. Heap/jank: `performance.memory.usedJSHeapSize`, frame times via a `requestAnimationFrame` sampler during a programmatic pan, long-task count; compare before/after at mobile viewport.
4. Functional parity: pin click opens event Analysis (not country), cluster click zooms in, list click flies to the pin, Local/Global and All/Major/Categories still filter, range selector changes both globe and list, Weather/Time Zone modes and storm markers unaffected, draw tool loads on first use, no console errors.
5. Production after deploy: first hourly sync archives the backlog; `X-Vercel-Cache: HIT` on repeat loads; spot-check on a real phone (the original crash case).
6. Backend suite green; new tests pass.

## Phase 13: ✅ IMPLEMENTED and verified (not yet committed or deployed)

Backend: `view=map`/`days`/`limit` on `/api/crises` (short window newest-first, long window severity-then-recency capped at 10k, hard ceiling 30k, edge `Cache-Control`), `services/retention.py` archive job wired into `scheduled_sync`, composite index + Alembic migration `b7d2e41f9a35`. 300 backend tests pass (+24 new). Frontend: clustered GPU pin layers (`globe/crisisLayers.ts`) replacing per-event DOM markers, one shared query for globe and list (removed the duplicate fetch), virtualized Events list, 24h/48h/7d selector, lazy-loaded draw tool and background, maplibre chunk split, mobile lite mode (1x DPR/30 fps/no extras for the background, no backdrop blur, pixelRatio cap), mobile layout overlap fix.

Measured, same gesture and 1280x800 viewport, production old build (28k DOM pins) vs new build against 26k synthetic 48h events: DOM nodes 227,349 → 179; JS heap 155 MB → 42 MB; list request 2 × 2.7 MB → 1 request (7.3 MB raw / 1.2 MB gz for 26k rows, vs 3.1 MB gz for 32k rows before); pan frames ~2,000 ms each (0.5 fps) → steady, zero frames over 50 ms; main JS 1.6 MB single chunk → 94 KB gz app + 281 KB gz cached maplibre chunk, draw tool (64 KB gz) deferred. Not measurable here: a real phone.

## Out of scope (revisit if volume keeps growing)

Viewport/bbox-driven loading or vector tiles for events, moving off the Werkzeug dev server to gunicorn+gevent, tightening GDELT ingestion volume itself, brotli at the origin, and a premium "event history" view over archived rows.

---

# Phase 14: Premium feature 1 — Satellite and Topography layers

## Context

First of the premium features (roadmap order: layers → dashboard → comments/follows/user pins → branch scenarios → groups/chat). Phase 12's foundation is in (`/api/me`, `useEntitlements`, `PremiumGate`), and `ModeSwitcher` holds a disabled "Satellite" placeholder. This phase replaces it with a real layer control: **Satellite** imagery and **Topography** (shaded relief everywhere, plus 3D terrain on desktop only), both premium.

Decisions made with the owner: imagery = **Sentinel-2 cloudless 2017 mosaic by EOX**; topography = **shaded relief + 3D terrain on desktop** (phones/low-core devices get relief only, since mobile crashes were the previous performance problem).

Researched and verified:
- EOX `s2cloudless-2017_3857`: **CC BY 4.0** (commercial use OK with attribution; 2018+ editions are non-commercial only, so the 2017 edition is deliberate). 10 m, zoom to 21. URL (HTTPS, 200 verified): `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2017_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg`.
- Elevation: AWS Terrain Tiles, Terrarium encoding, free with attribution (Mapzen/joerd, see its attribution doc). URL (200 verified): `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`. MapLibre v5 supports `raster-dem` hillshade and 3D terrain on the globe projection.
- Not used: Esri World Imagery (not licensed for commercial apps). NASA GIBS (free, 250 m daily) stays an optional later add-on.
- Base style (OpenFreeMap liberty) layer order: fills/water (0-18) → aeroway/tunnel/roads/bridges (19-82) → buildings (83-84) → `boundary_*` (85-87) → labels (88+). Inserting imagery **before `boundary_3`** covers fills, roads and buildings but keeps borders and labels on top (a clean "imagery + labels" look). Crisis layers are added last, so they stay above everything.

## 14.1 State and gating

- `state/uiStore.ts`: add `satellite: boolean`, `relief: boolean` and setters (both default off).
- Gating is enforced where the layers are applied, not only in the UI: `effectiveSatellite = premium && satellite`, so a user who loses premium (or is anonymous with stale state) never gets the layers. Honest limit: these are public third-party tile endpoints, so they can't be server-gated without proxying tiles through Flask (bandwidth, and EOX fair-use); client-side gating is the accepted tradeoff here. Server-side enforcement (`@require_premium`) is used for the features that serve our own data (dashboard, comments, pins, scenarios).

## 14.2 Layer module — `frontend/src/globe/baseLayers.ts` (new)

- `setSatellite(map, on)`: add/remove raster source `satellite-imagery` (256 px tiles, `maxzoom 13` so MapLibre overzooms beyond native detail, attribution string per EOX's own layer abstract/license page) and raster layer inserted `beforeId = first layer whose id starts with 'boundary_'`.
- `setRelief(map, on, { terrain3d })`: raster-dem sources `hillshade-dem` and `terrain-dem` (separate sources, as MapLibre recommends), a `hillshade` layer (lighter exaggeration over imagery than over the vector map) and, when `terrain3d`, `map.setTerrain({ source: 'terrain-dem', exaggeration: ~1.4 })`; `setTerrain(null)` when off. Hillshade `beforeId` = first `aeroway*` layer (below roads) on the standard map, or the same `boundary_*` anchor as the imagery when satellite is on (so it sits above the imagery); a small `reorder()` re-applies this whenever either toggle changes.
- Look layer ids up dynamically with a `firstLayerId(map, prefix)` helper rather than hard-coding indices; fall back to adding on top if an anchor is missing.
- Attribution strings: EOX (copy exactly from the layer's capabilities abstract at implementation time) and "Elevation: Mapzen / AWS Terrain Tiles" with a link to the joerd attribution doc.

## 14.3 Wiring

- `globe/Globe.tsx`: one effect, deps `[mapReady, satellite, relief, premium]`, that calls the two functions (`useEntitlements()` supplies `premium`; `terrain3d = !isLiteDevice()`). Removing layers on cleanup/turn-off must `removeLayer` before `removeSource`. Applies in all globe modes (Events/Weather/Time Zone).
- New `frontend/src/lite.ts` exporting `isLiteDevice()` (the same check now inlined in `background/SolarSystem.tsx`: `max-width: 768px` or `hardwareConcurrency <= 4`); `SolarSystem.tsx` switches to it so there's one definition.
- New `globe/LayerControl.tsx` (+ CSS module): small vertical stack under MapLibre's zoom control (top-right, ~120 px from the top) with two toggle buttons, "Satellite" and "Topography", each wrapped in `PremiumGate` (`feature` = "Satellite view" / "Topography"). Mounted in `App.tsx`. Remove the placeholder button and the `PremiumGate` import from `globe/ModeSwitcher.tsx`. Mobile: same stack; ensure it clears the draw-tool control and doesn't overlap the sidebars' edge tabs.
- `backend/app.py` `_CSP`: add `https://tiles.maps.eox.at` and `https://s3.amazonaws.com` to `connect-src` (img-src already allows `https:`). Only affects the Flask-served path; Vercel sets no CSP.

## 14.4 Tests and verification

- Backend: test that the CSP header includes the two new hosts (extend the existing `/api/health` header checks or add a small test).
- Frontend (no test runner exists): `tsc -b`, `vite build`, lint, then live in the browser using the local fake-Supabase + HS256 token technique from Phase 12 to exercise anonymous / free / premium:
  1. Anonymous and free: both buttons dimmed with lock and the right prompt; no imagery/relief requests in the network log even if store flags are forced on.
  2. Premium: Satellite shows imagery with borders and labels above it and crisis pins/clusters above both; Topography shows relief on the standard map and over imagery; both together; toggling off fully restores the base map (no leftover layers/sources, checked via `map.getStyle()`).
  3. Desktop: 3D terrain visible when pitched on mountains (Alps/Himalaya); phone viewport (375 px) and low-core: relief only, `map.getTerrain()` null, still smooth.
  4. Attribution text visible and correct; console clean; tile requests succeed (no CSP/CORS errors) on both the Vite dev server and the Flask-served `http://localhost:5000/`.
  5. Re-run the pan-frame-time sampler used in Phase 13 with Satellite+Topography on at desktop and mobile; confirm no regression to the earlier fix (no per-frame stalls, DOM node count unchanged).
- Backend suite stays green (`pytest`).

## After this phase

Next in order: dashboard (saved events, source filters, location alerts), then comments tab / follows / user pins ("User" tab) with report + auto-hide moderation, branch scenarios, groups and chat. Still owed on the asix.live side for any of it to work in production: the Railway/Vercel env vars, removing the login redirect for GeoIntel, the session handoff, and applying `001_geointel_profiles.sql`. Until then premium features stay locked for everyone.

## Phase 14: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `globe/baseLayers.ts` (`syncBaseLayers`), `globe/LayerControl.tsx` (+ CSS), `lite.ts` (`isLiteDevice`, now shared with `SolarSystem.tsx`), `backend/tests/test_security_headers.py`; wired via a `Globe.tsx` effect (`premium && toggle`), `uiStore` flags, CSP hosts added in `backend/app.py`; the Satellite placeholder is removed from `ModeSwitcher`. 304 backend tests pass; `tsc`, lint and build clean.

**Correction to the plan: the satellite source is EOX's 2016 edition (`s2cloudless_3857`), not 2017.** Verified live that the 2017 edition has blank white land across much of Africa even at zoom 6; the 2016 edition is also CC BY 4.0 and fully global. Attribution uses EOX's own wording for that layer ("Contains modified Copernicus Sentinel data 2016").

Verified in the browser with a fake-Supabase premium and free token: anonymous/free get locked, inert controls and zero imagery/DEM requests; premium gets Satellite (imagery under borders/labels, crisis pins above), Topography (hillshade above imagery, below borders; below roads on the plain map), both together, 3D terrain on desktop (Alps, pitched), and a full restore to the plain map when toggled off (no leftover layers/sources, terrain null). Phone viewport: layout clean, relief and imagery on, no 3D mesh, 199 DOM nodes. Console clean.

---

# Phase 15: Premium feature 2 — Branch scenarios ("multiple ways a crisis could unfold")

## Context

Next premium feature (pulled forward ahead of the dashboard; it needs no new tables). In the event Analysis panel, a premium user clicks **Show scenarios** and gets 3–4 AI-generated ways the situation could unfold. Decisions made with the owner: model **Claude Sonnet 5.5**; generate **on click** (not automatically); and point the existing AI features (briefing, history, country profile) at the same shared model setting.

Constraints from the codebase's own doctrine and from what exists:
- **No fabricated precision.** The old Forecast tab (probability buckets) was removed because it was heuristic arithmetic; the `forecasts` table was kept "to be rebuilt on a real model later". So scenarios carry **qualitative likelihood words only** ("less likely / plausible / more likely"), never percentages; are labelled AI-generated and speculative; list their assumptions; and show what real facts they were grounded in. Same spirit as `history.py`'s analogy "strength" word and its disclaimer.
- **No static fallback.** Unlike the briefing, there is nothing honest to show without a model, so with no `ANTHROPIC_API_KEY` (or on any AI failure) the endpoint returns 503 and the UI says scenario analysis isn't available right now — never a made-up set. Production currently has **no `ANTHROPIC_API_KEY`** (Railway vars: CORS_ORIGINS, FLASK_ENV, NEWSAPI_KEY, RESEND_API_KEY, DATABASE_URL), so the owner must add one before this works live.
- This is the first feature that serves our own computed data, so it uses the **server-side `@require_premium`** gate from Phase 12 (401 sign-in / 403 upgrade), not just a locked UI.
- Cost control: premium-only, on-click, 12 h cache per event (`cache.py`), a rate limit, and `max_tokens` capped (~1800).
- The existing AI call sites use `claude-3-5-sonnet-20241022`, which looks retired; centralise the model id.

## 15.1 Shared model setting

`backend/services/ai_client.py`: add `AI_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5-5')`. Switch `services/briefing.py` (the `create(...)` call and the `'model'` field of the result), `services/history.py` and `services/country_profile.py` to it, and update any test that asserts the old model string.

## 15.2 Backend — `backend/services/scenarios.py` (new)

- `generate_scenarios(crisis_id)`: returns the result dict, `None` if the crisis doesn't exist, raises `ScenariosUnavailable(reason)` when there's no API key or the model call/validation fails. Cached 12 h under `scenarios:{crisis_id}` via `cache_get/cache_set` (failures are never cached).
- Context (reused, not rebuilt): crisis fields; `analyze_escalation(crisis_id, _crisis=...)` for the real trend/velocity (services/escalation.py); the real source article description via `fetch_real_page_metadata(crisis.source_url)` (as `briefing.py` does); the curated relationship facts for the crisis's actor pair — extract the existing inline lookup in `history.py` into a small shared `get_relevant_relationships(session, crisis)` helper and call it from both.
- Model call: **forced tool use** (`record_scenarios`, JSON schema) so the output is structured without brittle text parsing: 3–4 scenarios, each `{title, likelihood ∈ {less likely, plausible, more likely}, timeframe (short free text), summary, what_would_drive_it[], watch_for[], who_is_affected[]}`, plus top-level `assumptions[]`. Prompt rules: span the range (de-escalation, persistence, escalation, optionally one wildcard); use only the provided facts for statements about the current situation and mark everything else as an assumption; **no percentages or numeric probabilities, no invented figures, quotes or named individuals**; if the context is thin, say so and keep scenarios general; scenarios are possibilities, not predictions.
- Server-side validation (`_validate`): coerce lists to short `list[str]`, drop scenarios with an unknown likelihood word, empty title/summary, or probability-style numbers (regex for "N% chance/probability/likely", "probability of N"); require ≥ 2 valid scenarios or raise `ScenariosUnavailable`.
- Result also carries `based_on` (severity, trend, whether real source text was available, the relationship(s) used), `model`, `timestamp` and a plain-language `disclaimer`.

## 15.3 Backend — endpoint

`backend/blueprints/crises.py`: `GET /api/crises/<crisis_id>/scenarios`, decorated `@limiter.limit("10 per minute")` then `@require_premium` (from `services/gating.py`); maps `None` → 404, `ScenariosUnavailable` → 503 `{error: 'scenarios_unavailable', reason}`, other exceptions → generic 500 like the sibling endpoints.

## 15.4 Frontend

- `api/types.ts`: `Scenario`, `ScenariosResponse`. `api/client.ts`: `fetchCrisisScenarios(id)` via `authedFetch`, throwing a typed error carrying the HTTP status so the UI can tell sign-in-required / premium-required / unavailable / other. `state/queries.ts`: `useCrisisScenariosQuery(id, enabled)` (`retry: false`, long `staleTime`).
- New `sidebars/analysis/Scenarios.tsx` + `Scenarios.module.css`: section "Possible scenarios". Non-premium: short description and a `PremiumGate`-wrapped (inert) **Show scenarios** button with the usual sign-in/upgrade prompt. Premium: button sets local `requested` state, which enables the query; loading text ("Analysing… this can take up to half a minute"); result cards with title, a muted likelihood chip, timeframe, summary, "What would drive it", "Watch for", "Who is affected"; an **Assumptions** list; a "Based on" line and the AI/speculative disclaimer. Honest error states for 503 ("Scenario analysis isn't available right now"), 401/403 (sign in / upgrade) and other failures. All text rendered as React text nodes (no HTML injection).
- `EventAnalysis.tsx`: render `<Scenarios key={crisis.id} crisisId={crisis.id} />` after the Analysis section so state resets per event.
- Mobile: single-column cards; check at 375 px.

## 15.5 Tests and verification

- `backend/tests/test_scenarios.py`: `_validate` (valid, bad likelihood dropped, probability-number text dropped, <2 valid raises); `generate_scenarios` with a fake Anthropic client returning a `tool_use` block (happy path, cache hit makes no second call, failure not cached, no key → `ScenariosUnavailable`, unknown crisis → `None`); endpoint tests reusing `test_gating.py`'s HS256-token + patched `_fetch_subscription` approach (anonymous 401, free 403, premium 200, 503 without key, 404 unknown id). Update any test asserting the old model id. Full backend suite stays green.
- Live check, no real API key needed: a scratchpad launcher that imports the app, patches `services.scenarios.anthropic_client` with a fake, and runs it together with the fake-Supabase server and minted premium/free tokens (the same technique as Phases 12/14; no test hooks added to product code). In the browser confirm: anonymous and free see the locked preview and the button does nothing; premium click → loading → cards; a second event resets the section; a forced 503 shows the honest unavailable message; no console errors; layout at 375 px.
- Owner-side smoke test with a real `ANTHROPIC_API_KEY` (set on Railway) once deployed — I can't run that from here.

## Phase 15: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `backend/services/scenarios.py`, `backend/tests/test_scenarios.py`, `frontend/src/sidebars/analysis/Scenarios.tsx` (+ CSS module). Changed: shared `AI_MODEL` in `services/ai_client.py` now used by briefing, history, country profile **and** `data_sources/geocoding.py` (a fourth call site with the same retired id, found while doing it); `get_relevant_relationships()` extracted from `history.py`; `GET /api/crises/<id>/scenarios` behind `@limiter` + `@require_premium`; `EventAnalysis.tsx` renders the section keyed per event. 335 backend tests pass (+31); `tsc`, lint and build clean.

Verified live with a fake AI client + fake Supabase + minted tokens (scratchpad launcher, no product-code hooks): anonymous/free get the locked intro (and a forced click on the inert button makes no request); premium click → loading → cards with qualitative chips, assumptions, "Based on" line and disclaimer; a scenario containing "30% chance" is dropped server-side; switching events resets the section; cached results return instantly; a failing model shows "isn't available right now" with Try again, and exactly one request is made (no silent retry); the dev demo flag unlocks the UI but the server still answers 401 ("Sign in to use scenarios"); phone layout is single-column and readable.

Bugs found and fixed during verification: (1) React Query silently refetched an errored scenarios query on window focus, a surprise paid call → `refetchOnWindowFocus`/`refetchOnReconnect` off for this query; (2) the section rendered blank if `requested` was true while not premium → it now falls back to the locked intro; (3) the Phase 14 layer buttons floated over the open Analysis panel and covered the chips → they now slide left of the panel (hidden on phones while it's open); (4) the probability-number filter missed "probability of collapse is about 60" → regex widened (caught by a test).

Not done / owner: add `ANTHROPIC_API_KEY` on Railway (none set today) and smoke-test with the real Sonnet 5.5 model; model id is `ANTHROPIC_MODEL`-overridable. Observed but out of scope: on phones the logo and mode switcher sit on top of an open sidebar's header.

---

# Phase 16: Premium feature 3 — User dashboard, first slice (saved events + outlet filter)

## Context

Third premium feature, first slice of the dashboard. Decisions made with the owner: this slice = **saved events + a hide-outlets filter** (location alerts/email, curated feed, messages, groups come in later slices as the features they depend on arrive); the dashboard is a **"My dashboard" overlay panel opened from the account chip**; the filter **hides specific outlets** (blocklist), because production shows ~2,750 distinct outlets in 48 h (940 to cover 80% of events, only 182 with 20+ events), so a checklist or allow-list is impractical.

Design facts:
- **Where user data lives and who can touch it:** two new Supabase tables with RLS enabled and **no policies**, so only the service-role key (server-side, already used for entitlements in Phase 12 — no new env vars) can read or write them. Users can't reach the tables directly; every access goes through Flask, which verifies the JWT, enforces premium with `@require_premium`, and always scopes by the verified user id. Simpler and safer than shipping a Supabase client to the browser, and consistent with the Phase 12/15 pattern.
- **Saved events must outlive the event.** The retention job archives events after 7 days, so a save stores a **snapshot** (title, country, type, severity, lat/lon, source_url, event date) taken **server-side from our own `crises` row**, never from client-sent fields. Archived rows still exist, so the existing briefing/detail endpoints keep working for a saved event.
- The outlet filter keys on the hostname of `source_url` (lowercased, leading `www.` stripped). Events without a `source_url` have no outlet and are never hidden.

## 16.1 Supabase schema — `backend/supabase/002_geointel_user_data.sql` (owner applies)

- `geointel_saved_events(user_id uuid → auth.users on delete cascade, crisis_id text, title, country, type, severity int, lat/lon double precision, source_url, event_date timestamptz, saved_at timestamptz default now(), primary key (user_id, crisis_id))`.
- `geointel_user_prefs(user_id uuid primary key → auth.users on delete cascade, hidden_outlets text[] not null default '{}', updated_at timestamptz default now())`.
- `enable row level security` on both, deliberately no policies (service role only), with a comment saying why.

## 16.2 Backend

- `backend/services/user_data.py` (new): a small PostgREST helper reusing the `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` pattern from `services/entitlements.py`; raises `UserDataUnavailable` when unconfigured or on any network/HTTP error. Functions: `list_saved(user_id)` (newest first, cap 500), `save_event(user_id, crisis)` (upsert on `(user_id, crisis_id)`, snapshot from the `Crisis` row, 500-save cap → `SaveLimitReached`), `unsave_event(user_id, crisis_id)`, `get_prefs(user_id)`, `set_prefs(user_id, hidden_outlets)` — normalise (lowercase, strip `www.`, hostname regex, dedupe) and cap at 1,000, rejecting invalid input.
- `backend/blueprints/dashboard.py` (new, registered in `app.py`), all `@limiter.limit("60 per minute")` + `@require_premium`: `GET /api/me/saved`, `PUT /api/me/saved/<crisis_id>` (idempotent; 404 unknown crisis; 409 at the cap), `DELETE /api/me/saved/<crisis_id>`, `GET /api/me/prefs`, `PUT /api/me/prefs` (400 on invalid body). `UserDataUnavailable` → 503 `{error: 'user_data_unavailable'}`.

## 16.3 Frontend

- `api/types.ts` + `api/client.ts`: `SavedEvent`, `UserPrefs`; `fetchSaved/saveEvent/unsaveEvent/fetchPrefs/savePrefs` through `authedFetch`, with a typed error (like `ScenariosError`) so the UI can say sign-in / upgrade / unavailable.
- `state/queries.ts`: `useSavedEventsQuery`, `usePrefsQuery` (both `enabled` only when premium), save/unsave/prefs mutations that invalidate or optimistically update; **no refetch-on-focus surprises**. New `useVisibleCrises(scope, range)` = `useCrisesQuery` result minus events whose outlet is in the user's hidden set (premium users only; memoised; a regex hostname extractor in a new `lib/outlet.ts` so 20k+ events stay cheap). `EventsSidebar.tsx` and `globe/Globe.tsx` both switch to it so the list, its count and the globe stay in sync.
- `state/uiStore.ts`: `dashboardOpen` (+ setter) and `dashboardTab: 'saved' | 'sources'`.
- `components/SaveButton.tsx`: a Save / Saved toggle in `EventAnalysis.tsx`'s meta row; locked via `PremiumGate` for non-premium.
- `components/Dashboard.tsx` (+ CSS module): centered overlay, full-screen on phones, Esc/backdrop/× to close.
  - **Saved** tab: saved events newest first (title, country, severity dot, saved date, remove ×); clicking one selects it (`selectCrisis` from the snapshot), closes the overlay and opens the Analysis sidebar; empty state explains how to save.
  - **Sources** tab: a search box over the outlets present in the current data (with event counts), a "most frequent right now" quick list, and a "Hidden outlets" list with unhide ×; a line like "3 outlets hidden · 412 events currently hidden".
- `components/AccountChip.tsx`: add a **Dashboard** button (opens the overlay; wrapped in `PremiumGate` so non-premium visitors see it locked).

## 16.4 Tests and verification

- `backend/tests/test_user_data.py`: service layer against an in-memory fake of the PostgREST calls — snapshot comes from the DB row not the client, upsert is idempotent, ordering, unsave, 500 cap, prefs normalisation/dedupe/caps/invalid input, unconfigured and HTTP-error → `UserDataUnavailable`. `backend/tests/test_dashboard_endpoints.py`: 401 anonymous, 403 free (and no Supabase call made), premium happy paths, 404/409/400/503, user A can't see user B's saves (scoping by verified id).
- Live check (no real Supabase needed): extend the scratch fake-Supabase server to emulate the two tables, run with minted premium/free tokens as in Phases 12/14/15. In the browser: anonymous/free see the locked Dashboard and Save buttons (forced click makes no request); premium saves an event, sees it in the dashboard, reload persists it, unsave removes it; clicking a saved item opens its Analysis; hiding an outlet removes its events from both the list (count drops) and the globe and survives reload; unhide restores them; a saved event whose crisis was archived still opens; phone layout; console clean. Backend suite and `tsc`/lint/build stay green.
- Owner: apply `002_geointel_user_data.sql` in Supabase (no new env vars).

## Later slices (unchanged order)

Alert location + email alerts (Resend), curated feed, comments/follows/user pins, groups/chat — each adds its own tables and a dashboard tab.

## Phase 16: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `backend/supabase/002_geointel_user_data.sql`, `services/user_data.py`, `blueprints/dashboard.py`, `tests/test_user_data.py` (47 tests); frontend `lib/outlet.ts`, `components/Dashboard.tsx`, `components/SaveButton.tsx`, dashboard hooks in `state/queries.ts` incl. `useVisibleCrises` (now read by `EventsSidebar` and `Globe`), dashboard state in `uiStore`, Dashboard button in `AccountChip`, Save in `EventAnalysis`. 382 backend tests pass; `tsc`, lint, build clean.

Verified live (fake Supabase emulating the two tables + minted tokens): API 401/403/200, per-user isolation, 400 on bad outlets; premium saves an event ("★ Saved"), it appears in the dashboard, survives a reload, opens in Analysis; an **archived** event (not in the live list) saved from its server-side snapshot still opens with its analysis; hiding `dailymail.com` removed exactly its 51 events from the list (4,109 → 4,058) and the globe agreed (4,058 events across pins, checked via the map source), persisted across reload, and "Show again" restored both to 4,109; free users see locked inert Dashboard/Save and forced clicks send nothing and open nothing; the dev demo flag unlocks the UI but the server answers 401 ("Sign in to use your dashboard"); phone layout is full-screen.

Fixed along the way: Dashboard overlay renders only for premium (a forced click on the locked button used to open an empty one); Save button sends nothing unless premium; mobile panel made fully opaque. Dev-server note: Vite served a stale cached module once after a scripted edit (`?t=` URL unchanged) — touching the file fixed it; not a code issue.

Owner: apply `002_geointel_user_data.sql` in Supabase (no new env vars — uses the existing service-role key).

Housekeeping since: the paused pin-grouping experiment was dropped — `crisisLayers.ts`/`Globe.tsx` are back to one pin and one cluster-count unit per event (click opens that event's popup and Analysis), keeping only the centre-without-zoom click behaviour; verified live.

---

# Phase 17: Premium feature 4 — Comments tab and moderation (social slice 1)

## Context

First slice of the user network. Decisions made with the owner: build **Comments + moderation only** (follows and user-submitted pins reuse this identity/moderation layer, so they are the next slices); **free users can read, premium users can post**; a reported comment is **auto-hidden after 5 different people report it**; the owner reviews reports through **admin API endpoints** (existing admin key / admin-email check) for now, no admin UI.

Design facts:
- A **Comments** tab joins the event Analysis view (Analysis | Comments); the country view is unchanged.
- Identity: the `geointel_profiles` table from Phase 12 (public display name). A premium user picks a **display name** the first time they post. Names are 2-40 chars and **unique case-insensitively** (new unique index) so nobody can impersonate another user. The comment row stores an `author_name` **snapshot**, which avoids joins and keeps old comments readable after a rename.
- Same access pattern as Phase 16: new tables have RLS on and **no policies**; only the Flask backend (service-role key, existing env vars) touches them, scoped to the verified user. Reading comments is public (through Flask), so anonymous and free visitors can read them.
- Comments are plain text only (rendered as text, links not clickable), max 1,000 chars, rate-limited, and tied to a crisis id; they survive the event being archived.
- Moderation visibility: a **hidden** comment is shown only to its author (flagged "hidden pending review") and the admin; **removed** comments are never served.

## 17.1 Supabase schema — `backend/supabase/003_geointel_comments.sql` (owner applies)

- `geointel_comments(id uuid pk default gen_random_uuid(), crisis_id text, user_id uuid -> geointel_profiles(user_id) on delete cascade, author_name text, body text check (1..1000 chars), status text check in ('visible','hidden','removed') default 'visible', report_count int default 0, created_at timestamptz default now())` + index on `(crisis_id, created_at desc)`.
- `geointel_comment_reports(comment_id -> comments on delete cascade, reporter_id -> auth.users on delete cascade, reason text, created_at, primary key (comment_id, reporter_id))` — one report per person per comment.
- `create unique index on geointel_profiles (lower(display_name))`; RLS enabled on both new tables with no policies (explained in a comment).

## 17.2 Backend

- Small refactor: move the PostgREST helper and the unavailable-exception out of `services/user_data.py` into `services/supabase_rest.py` (`rest()`, `SupabaseUnavailable`, uuid check) and import them back (`UserDataUnavailable` stays as an alias), so comments reuse it; existing tests keep passing.
- `services/gating.py`: add `require_user` (verified signed-in user, 401 otherwise; no premium check) for actions a lapsed-premium author must still be able to do (deleting their own comment).
- `services/comments.py` (new): `get_profile` / `set_profile(user_id, display_name)` (trim, collapse spaces, strip control chars, 2-40 chars, unique → `DisplayNameTaken`), `list_comments(crisis_id, viewer_id, limit=50, before=None)` (newest first; visible rows plus the viewer's own hidden ones, merged), `post_comment(user_id, crisis_id, body)` (crisis must exist; profile required; body cleaned and length-checked; 10 s per-user cooldown → `TooFast`), `delete_own_comment`, `report_comment(reporter_id, comment_id, reason)` (cannot report your own; idempotent per reporter; after inserting recount distinct reporters, store `report_count`, and set `hidden` when the count reaches `AUTO_HIDE_THRESHOLD = 5`), and admin helpers `list_reported`, `restore` (clear reports, set visible), `remove` (set removed).
- `blueprints/comments.py` (new, registered in `app.py`): `GET /api/crises/<id>/comments` (public, `optional_user` so a viewer's own hidden comments appear, 60/min), `POST /api/crises/<id>/comments` (`@require_premium`, 10/min; 404 unknown crisis, 409 `profile_required`, 400 invalid body, 429 `slow_down`), `DELETE /api/comments/<id>` (`@require_user`, own comments only), `POST /api/comments/<id>/report` (`@require_premium`, body `{reason}` from a fixed list), `GET`/`PUT /api/me/profile` (`@require_premium`; 409 when the name is taken), and admin endpoints guarded by the existing `check_admin_key()`: `GET /api/admin/comments/reported`, `GET /api/admin/comments/<id>/reports`, `POST /api/admin/comments/<id>/restore`, `POST /api/admin/comments/<id>/remove`. `SupabaseUnavailable` -> 503 like the dashboard endpoints.

## 17.3 Frontend

- `api/types.ts` + `api/client.ts`: `Comment`, `Profile`, and calls (`fetchComments` via `authedFetch` so the token is sent when present, `postComment`, `deleteComment`, `reportComment`, `fetchProfile`, `saveProfile`) with a typed error (sign-in / upgrade / profile-required / name-taken / slow-down / unavailable), following the `UserDataError` pattern.
- `state/queries.ts`: `useCommentsQuery(crisisId)` (no refetch-on-focus), post/delete/report mutations that invalidate it, `useProfileQuery` (premium only) and `useSaveProfileMutation`.
- `sidebars/analysis/EventAnalysis.tsx`: tab row (Analysis | Comments) under the meta row; the existing content moves under the Analysis tab untouched; the tab resets per event. New `sidebars/analysis/Comments.tsx` (+ CSS module): list with author, relative time, plain-text body, "Show more"; own comments get Delete, others' get Report (inline reason picker, then "Reported, thanks"); hidden-own comments are labelled; composer with a 1,000-char counter; premium user with no profile first sees an inline "Choose a display name" form; free/anonymous visitors see the list plus a locked composer (`PremiumGate`) with the usual sign-in/upgrade prompt. Honest error states throughout; forced clicks on locked controls send nothing (same guards as Phases 15/16).

## 17.4 Tests and verification

- Backend: a small shared in-memory PostgREST emulator for tests (eq/lt/gt/in filters, order, limit, select, upsert/ignore-duplicates, PATCH, DELETE). `tests/test_comments.py`: display-name rules incl. case-insensitive uniqueness; posting requires profile and premium, body cleaning/limits, cooldown, unknown crisis; listing newest-first with paging, hidden/removed visibility rules for author/other/anonymous; deleting only your own; reporting (not your own, idempotent, counts distinct reporters, hides at exactly 5, never re-hides a restored comment unless 5 new reports); admin endpoints reject without the admin key and restore/remove correctly; 401/403 matrix and 503 paths. Full suite stays green.
- Live check with the scratch fake Supabase (extended for the new tables) and minted tokens, as in Phases 12-16: anonymous/free read comments and see a locked composer (forced click sends nothing); premium without a profile is asked for a display name, then posts; the comment appears for another user; a second premium user reports it and a third..fifth reports hide it for everyone but the author (who sees the hidden label) and an admin call restores it; delete own; error states (taken name, slow down, unavailable); phone layout; console clean.
- Owner: apply `003_geointel_comments.sql`; use the admin endpoints (documented with curl examples in `backend/README.md`) to review reports. No new env vars.

## Out of scope (next slices)

Follows (follow/unfollow, Following list), user-submitted pins and the "User" tab, blocking users, editing comments, avatars, notifications, and an admin UI.

## Phase 17: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `backend/supabase/003_geointel_comments.sql`, `services/supabase_rest.py` (shared PostgREST helper, `user_data.py` now uses it), `services/comments.py`, `blueprints/comments.py`, `tests/supabase_fake.py` (in-memory PostgREST emulator), `tests/test_comments.py` (71 tests); `require_user` in `services/gating.py`; frontend `sidebars/analysis/Comments.tsx` (+ CSS), Analysis | Comments tabs in `EventAnalysis.tsx`, comment/profile hooks and client calls. 453 backend tests pass; `tsc` and build clean, lint shows warnings only.

Verified live (fake Supabase + minted tokens): API moderation flow (profile 409, name-taken 409, post 201, cooldown 429, 4 reports no hide / 5th hides, anonymous sees none, author sees own hidden comment flagged, admin 401 without key, list/restore, delete own); UI: posting with literal plain-text rendering of HTML/URLs, cooldown message, Delete only on own comments, display-name form with taken-name error then success, Report with reason picker then "Reported", anonymous read-only with disabled composer, no Report/Delete links and a forced click sending no request, phone layout.

Owner: apply `003_geointel_comments.sql` (after `002`); review reports via the admin endpoints (curl examples in `backend/README.md`). No new env vars.

---

# Phase 18: Enterprise weather, slice 1 — point-and-click forecast

## Context

Weather mode shows GDACS hazards and radar, but nothing says what the weather *is* or *will be* at a place. First step toward an enterprise weather tool (the owner's roadmap: forecast + watchlists/alerts first; source-health and licensed radar later). Decisions made with the owner: forecast data from **Open-Meteo, behind one provider module, with a switch to its commercial key before launch**. Verified: Open-Meteo's free API is **non-commercial only** (<10,000 calls/day, 600/min, CC BY 4.0), so the free tier is for development; the paid key is a launch gate, not a code change.

Verified live: one call to `api.open-meteo.com/v1/forecast` returns `current` (temp, feels-like, humidity, precipitation, WMO weather code, wind speed/gusts/direction, pressure, cloud cover, visibility), `hourly` (168 h) and `daily` (7 days) in a single request.

## 18.1 Backend

- New `backend/services/forecast.py`: `get_forecast(lat, lon)` validates ranges, **rounds coordinates to 0.1 degrees** (about the model's grid, and what makes caching effective), caches 15 minutes via `cache.py` (key `forecast:{lat}:{lon}`), calls Open-Meteo once for current + next-48 h hourly + 7-day daily, and returns a trimmed, unit-labelled dict (metric; the UI converts) with `source`, `generated_at` and the grid point actually used. `None`/`ForecastUnavailable` on any upstream failure — never a made-up forecast. Provider base URL and optional key come from env (`OPEN_METEO_API_KEY` → `customer-api.open-meteo.com` + `apikey` param; unset → free endpoint), so launch is a config change.
- `backend/blueprints/weather.py`: `GET /api/weather/forecast?lat=&lon=` (public, `@limiter.limit("30 per minute")`; 400 bad/out-of-range, 503 unavailable). Existing `/storms` untouched.
- Reuse: `cache.py` (`cache_get/cache_set`), `limiter` from `extensions.py`, blueprint registration already covers `weather_bp`.
- CSP not needed (browser calls our own `/api`).

## 18.2 Frontend

- `uiStore`: new selection kind `{ kind: 'point'; lat; lon; label: string | null }` + `selectPoint(lat, lon, label)`; `PinnedSelection` handled in `AnalysisSidebar` like the others.
- `Globe.tsx`: in **Weather mode only**, a click on the map that isn't a hazard pin selects a point instead of a country (the existing country hit-layer handler already runs in weather mode; branch on `activeModeRef.current === 'weather'` and use the clicked `lngLat`, taking the country name from the hit feature as the label). Drop a small marker at the selected point; remove it on mode change. Hazard pins keep stopping propagation, so they are unaffected.
- `api/client.ts` + `api/types.ts`: `fetchForecast(lat, lon)`, `Forecast` types. `state/queries.ts`: `useForecastQuery(lat, lon)` (`staleTime` 15 min, no refetch on focus, `retry: false`).
- New `sidebars/analysis/PointForecast.tsx` (+ CSS module, reusing `EventAnalysis.module.css` section styles): current conditions block, next-24 h strip (temp, rain chance, gusts), 7-day table (icon from WMO code, high/low, rain mm, max gust), a °C/°F and km/h/mph toggle (stored in `localStorage`, wrapped in try/catch), honest loading/unavailable states, source line "Open-Meteo, CC BY 4.0" with link. A small `lib/weatherCodes.ts` maps WMO codes to label + emoji (a fixed published table).
- Attribution requirement of the free licence is met by the source line; keep it when the key changes.

## 18.3 Tests and verification

- `backend/tests/test_forecast.py`: coordinate validation and rounding, cache hit makes no second call, upstream error/timeout/garbage → unavailable (not cached), response trimmed to the expected keys, API key param added only when env set; endpoint 400/503/200 and rate limit.
- Live: click several places in Weather mode (land, ocean, near a hazard pin, near the poles/antimeridian), check numbers against Open-Meteo's own site for one location, hazard-pin click still opens hazard analysis (not a point), Events/Time Zone modes unchanged, unit toggle persists, phone layout, console clean. `pytest`, `tsc`, lint, build stay green.

---

# Phase 19: Enterprise weather, slice 2 — watchlist places and alerts

## Context

The enterprise feature: customers save the places that matter to them (ports, plants, offices) and get alerted when a GDACS hazard comes near. Premium-only, server-enforced, same Supabase pattern as Phases 16/17 (RLS on, no policies; Flask uses the service-role key and scopes by the verified user). Decisions made with the owner: delivery = **in-app plus email via Resend**; watchlist item = **named point with a radius**.

Facts from exploration: there is **no email-sending code yet** (a `RESEND_API_KEY` exists on Railway); the scheduler (`init_scheduler` in `app.py`, APScheduler) runs one hourly sync job and the process runs from `python app.py`; hazards come from `services/weather.get_active_storms()` (5-minute cache); `services/supabase_rest.py` (`rest`, `check_uuid`, `SupabaseUnavailable`) and the in-memory PostgREST emulator `tests/supabase_fake.py` (supports upsert / ignore-duplicates) are reusable; no distance helper exists in the backend. `geointel_user_prefs` exists with `hidden_outlets`; `set_prefs` upserts with merge-duplicates, so adding columns does not clobber them.

## 19.1 Supabase schema — `backend/supabase/004_geointel_watchlist.sql` (owner applies)

- `geointel_watch_places(id uuid pk default gen_random_uuid(), user_id uuid -> auth.users on delete cascade, name text check 1..80, lat, lon double precision with range checks, radius_km integer check 10..2000, created_at)`; index on `(user_id, created_at)`; unique `(user_id, lower(name))`.
- `geointel_alerts(id uuid pk, user_id -> auth.users cascade, place_id -> geointel_watch_places cascade, hazard_key text, hazard_type text, title text, alert_level text, distance_km numeric, created_at, read_at timestamptz null, emailed_at timestamptz null)`; **unique `(place_id, hazard_key)`** (the dedupe guarantee); index on `(user_id, created_at desc)`.
- `alter table geointel_user_prefs add column alert_email boolean not null default true, add column alert_min_level text not null default 'orange' check in ('green','orange','red')`.
- RLS enabled on both new tables, no policies (commented, as in 002/003).

## 19.2 Backend

- `backend/services/geo.py` (new): `distance_km(lat1, lon1, lat2, lon2)` (haversine) — shared by alerts and the nearby-hazards view.
- `backend/services/watchlist.py` (new): `list_places`, `add_place` (cap **25 per user**, validates name/lat/lon/radius, duplicate name → `PlaceExists`), `delete_place`, `nearby_hazards(place, storms)` (hazards within radius, nearest first, from the cached storm list), and `list_alerts(user, limit=50)`, `mark_alerts_read(user, ids|all)`, `unread_count`. All scoped by verified user id, via `supabase_rest.rest`.
- `backend/services/alerts.py` (new): `evaluate_alerts()` — loads all watch places (paged, capped), loads each owner's prefs (min level, email on/off), gets hazards from `get_active_storms()` (skips quietly if `None`), and for every (place, hazard within radius, level >= user's minimum) builds `hazard_key = f"{event_type}-{id}-{alert_level}"` so an **escalation (Green→Orange) alerts again**, then inserts with `Prefer: resolution=ignore-duplicates,return=representation` so only genuinely new rows come back. Then, per user, **one digest email** for the newly inserted rows (not one per hazard), and `emailed_at` is set only after a successful send (a failed send is retried next run, and never re-alerts in-app).
- `backend/services/mailer.py` (new): `send_email(to, subject, html, text)` via Resend's HTTP API (`RESEND_API_KEY`, `ALERT_FROM_EMAIL` env; unconfigured → log once and return False, so in-app alerts still work). Plain-text part always included; HTML-escaped content; footer links to the dashboard where email can be switched off. Recipient address comes from Supabase Auth admin lookup (`GET {SUPABASE_URL}/auth/v1/admin/users/{id}` with the service-role key), added to `supabase_rest.py` as `auth_user_email(user_id)`, cached per run.
- Scheduler: `init_scheduler()` gains a second job `evaluate_alerts`, every **15 minutes** (`id='alert_eval'`, `replace_existing=True`, `max_instances=1`, wrapped in try/except so it never breaks the sync job).
- `backend/blueprints/watchlist.py` (new, registered in `app.py`, prefix `/api/me`), all `@limiter.limit("60 per minute")`: `GET/POST /watch` (`@require_premium`; GET returns places each with `nearby` hazards), `DELETE /watch/<id>` (`@require_user`, so a lapsed member can still clean up), `GET /alerts` (`@require_premium`; list + `unread`), `POST /alerts/read` (`@require_user`), `GET /geo/search?q=` (`@require_premium`, 20/min) proxying Open-Meteo geocoding (same provider module and key switch as 18.1; results trimmed to name/country/admin1/lat/lon, cached), and the existing `/prefs` endpoints extended with `alert_email` and `alert_min_level` (validated). 404 unknown id, 409 duplicate name / cap, 503 on `SupabaseUnavailable`.

## 19.3 Frontend

- `api/types.ts`, `api/client.ts`: `WatchPlace` (+ `nearby`), `AlertItem`, `GeoResult`; `fetchWatch/addPlace/deletePlace/fetchAlerts/markAlertsRead/searchPlaces`, typed `WatchError` like `UserDataError`. `state/queries.ts`: matching hooks (premium-only, no refetch-on-focus); `useAlertsQuery` polls every 5 minutes while the tab is visible so the badge updates.
- `components/Dashboard.tsx`: two new tabs, **Watchlist** (place list with radius, nearby-hazard chips and "nothing nearby" state; add form with place search + radius; delete with the same two-step confirm; cap message) and **Alerts** (newest first, level colour, distance, time, unread dot; "Mark all read"; clicking an alert selects that hazard — reusing `selectHazard` — closes the overlay and opens Analysis). Email settings row (on/off, minimum level) in the Alerts tab. `uiStore.DashboardTab` extended.
- `components/AccountChip.tsx`: unread-alert badge on the Dashboard button.
- `PointForecast.tsx` (from Phase 18): **"Add to watchlist"** button (wrapped in `PremiumGate`) that pre-fills the add form with the clicked point; `uiStore` carries a `pendingWatchPoint` so the Dashboard opens on the Watchlist tab with it filled in.
- Weather mode: watched places drawn as small markers (premium users only), hidden on the far hemisphere like the other DOM markers.
- Forced clicks on locked controls send nothing (same guards as Phases 15–17); all text rendered as plain React text.

## 19.4 Tests and verification

- Backend (extend `tests/supabase_fake.py` only if needed): `test_geo.py` (haversine known distances, antimeridian, poles); `test_watchlist.py` (validation, 25 cap, duplicate name 409, per-user isolation, delete own only, nearby ordering and radius edge, 401/403 matrix incl. lapsed-premium delete); `test_alerts.py` (new alert inserted once and not again on the next run, escalation alerts again, below-minimum level skipped, outside radius skipped, GDACS unavailable → no-op, one digest email per user with only new rows, `emailed_at` set only on success, failed send retried without re-alerting, email off or Resend unconfigured → in-app only, user with no email address handled); `test_mailer.py` (request shape, escaping, failure handling). Full suite stays green.
- Live (scratch fake Supabase + fake Resend HTTP server + minted tokens, as in Phases 15–17; no product-code test hooks): add a place near a live hazard and trigger `evaluate_alerts()` → alert appears in-app with the badge; run again → no duplicate; fake Resend receives exactly one digest; add place from a point forecast; free/anonymous see locked controls and a forced click sends nothing; delete flow; phone layout; console clean.
- Owner actions: apply `004_geointel_watchlist.sql`; on Railway set `ALERT_FROM_EMAIL` (a sender on a domain verified in Resend); `RESEND_API_KEY` is already set. Before any paid launch: set `OPEN_METEO_API_KEY` (commercial plan) — and revisit radar licensing (separate item).

## Out of scope (later slices)

Webhook/Slack delivery, drawn regions/routes, per-place alert rules, organisations/seats/roles, public API keys, source-health status page, licensed radar swap, forecast model layers (wind/temperature maps), SMS.

## Phase 18: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `backend/services/forecast.py` (Open-Meteo provider module; `OPEN_METEO_API_KEY` switches to the commercial host), `GET /api/weather/forecast`, `tests/test_forecast.py`; frontend `PointForecast.tsx` (+ CSS), `lib/weatherCodes.ts`, `lib/units.ts`, `point` selection in `uiStore`, Weather-mode map click in `Globe.tsx` (opens the Analysis panel; hazard pins unaffected; Events mode keeps the country click). Verified live: Houston/Chad/ocean points, unit toggle persists, hazard pin still opens its hazard, 503 shows an honest message and "Try again" recovers, phone layout.

Also in this stretch (before the plan): Weather mode shows cyclones, floods, wildfires and droughts from GDACS (64 live pins), clickable pins with a `HazardAnalysis` view, a legend with filters, a Weather list in the left sidebar, and animated RainViewer radar (512 px tiles and every second frame to stay under RainViewer's per-IP limit; one still frame on phones).

## Phase 19: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New backend: `supabase/004_geointel_watchlist.sql`, `services/geo.py`, `watchlist.py`, `alerts.py`, `mailer.py`, `geocode.py`, `blueprints/watchlist.py`, `auth_user_email` in `supabase_rest.py`, scheduler job `alert_eval` (15 min), and 168 new tests (654 total pass). Deviation from the plan: alert settings use their own `/api/me/alert-settings` endpoint rather than extending `/api/me/prefs`, so the existing prefs contract and tests stay untouched. New frontend: `WatchlistTab.tsx`, `AlertsTab.tsx`, `Watchlist.module.css`, Dashboard tabs, unread badge on the account chip, "Add to watchlist" in the forecast panel, watched places drawn in Weather mode.

Verified live with a fake Supabase, fake Resend and minted tokens against the real GDACS feed: alert created and emailed once, not repeated on the next run, a failed send retried without a duplicate alert, users isolated, free/anonymous locked with forced clicks sending nothing, alert click opens the hazard in Weather mode, add/search (real geocoding)/two-step remove, phone layout.

Owner: apply `004_geointel_watchlist.sql`; set `ALERT_FROM_EMAIL` (sender on a Resend-verified domain). Before any paid launch: set `OPEN_METEO_API_KEY` (commercial plan) and revisit radar licensing.

---

# Phase 20: More accurate pins — refine event locations from the article

## Context

GDELT places each event at the centre of the place its article names (city, state or country), not at the site, so pins pile up (56% of active events sit on 249 points) and country-level events land on meaningless spots such as the middle of Kansas. Decisions made with the owner: refine locations **from the article text** (AI picks the specific place, Nominatim geocodes it), via a **background job for Major events plus on-open for premium users**, and **everyone sees refined pins** (it is shared map data, not a feature; lookups are triggered by the system or by premium users, never by anonymous visitors).

Findings from exploration:
- `GET /api/crises/<id>/real-headline` (`blueprints/crises.py`) already does this on first open and saves the new position (`location_confidence = 90`), **but the new frontend never calls it**: dead code today. It is also public (anyone can trigger paid AI), uses the default Sonnet model (`AI_MODEL`) for a 40-token task, and only remembers "already tried" in an in-process cache, so a restart repeats the paid work.
- `DataAggregator._upsert_crisis` (`data_sources/__init__.py`) overwrites every field of an existing row, so a re-ingested event would silently undo a refinement.
- Reusable: `_extract_incident_location` and `NominatimGeocoder` (`data_sources/geocoding.py`, already 1 request/second and cached), `fetch_real_page_metadata` (`data_sources/utils.py`), `Crisis.location_confidence`, the APScheduler setup (`init_scheduler` in `app.py`), `require_premium`.
- Volume is small: 234 Major global GDELT events in the last 48 h (about 3,000 over 7 days), so cost is a few dollars a month with the cheap model.
- No `ANTHROPIC_API_KEY` locally or on Railway yet, so the real model can only be smoke-tested by the owner after deploy.

## 20.1 Data model

- Alembic migration (after `b7d2e41f9a35`): `crises.location_refined_at` (DateTime, null) and `crises.location_refined_name` (String 200, null). `refined_at` set means a definitive attempt finished; `refined_name` null with `refined_at` set means "tried, no usable location" (never retried).
- `Crisis.to_dict()` exposes `source`, `location_refined_name` and `location_refined_at` so the Analysis panel can decide what to show and whether to trigger a refinement.

## 20.2 Backend — `backend/services/location_refine.py` (new)

- `refine_crisis_location(crisis_id)` returns `{status: 'refined'|'none'|'unavailable'|'not_found', location?}`:
  1. Only GDELT rows (other sources carry their own coordinates). If `location_refined_at` is already set, return the stored outcome with **no external calls**.
  2. `fetch_real_page_metadata(source_url)` for the headline and description.
  3. Ask the model for the single most specific place (`_extract_incident_location`), now on a cheap model: new `AI_LOCATION_MODEL` in `services/ai_client.py` (env `ANTHROPIC_LOCATION_MODEL`, default Haiku 4.5), separate from the shared `AI_MODEL`.
  4. Geocode with `NominatimGeocoder.geocode`.
  5. **Sanity checks, conservative on purpose**: reject when the place name is just the country, when Nominatim returns no country, or when its country does not match the event's country. Country comparison uses a small normaliser plus alias table (Russia/Russian Federation, Czechia/Czech Republic, Türkiye/Turkey, Myanmar (Burma), Palestine, Congo variants); an unknown mismatch is a rejection, so we get fewer refinements but never a wrong country.
  6. Persist: latitude, longitude, `location_confidence = 90`, `location_refined_name`, `location_refined_at`; for a definitive "none" set `location_refined_at` only. A transient failure (no API key, network error, Nominatim down) returns `unavailable` and is **not** persisted, so it is retried later.
  7. On success `cache_clear_prefix('crises:')`. A process-wide lock prevents two threads refining the same event twice.
- `refine_pending(limit)`: picks GDELT, active, `scope='global'`, severity >= 70, `location_refined_at is null` rows (worst first, then newest) and refines up to `limit`; stops early after 3 consecutive `unavailable` results (AI or Nominatim down) or when a time budget (about 8 minutes) is spent. Returns a summary dict and never raises.
- `data_sources/__init__.py` `_upsert_crisis`: do not overwrite `latitude`, `longitude`, `country` or `location_confidence` on a row whose `location_refined_at` is set.
- Remove the refinement block from `real-headline` (it keeps returning the title, which sync now resolves anyway); its tests move to the new service tests.
- `app.py`: second scheduler job `location_refine` every 20 minutes (`max_instances=1`, `coalesce=True`, wrapped in try/except like `alert_eval`), `limit` from env `LOCATION_REFINE_PER_RUN` (default 60; `0` disables).
- `blueprints/crises.py`: `POST /api/crises/<id>/refine-location`, `@limiter.limit("20 per minute")` + `@require_premium`. 404 unknown id, 503 when unavailable, 200 with the status above.

## 20.3 Frontend

- `api/types.ts` / `api/client.ts`: add the three detail fields; `refineCrisisLocation(id)` through `authedFetch`.
- `state/queries.ts`: `useRefineLocationMutation()`. On a `refined` result it **patches the cached lean lists in place** (`setQueriesData` on the crises queries: update that event's lat/lon) instead of refetching the 1.2 MB list, and returns the new position.
- `EventAnalysis.tsx`: for a premium user, when the detail shows a GDELT event with no `location_refined_at`, call the mutation once on open. On success, re-select the crisis with its new coordinates so the globe recentres on the better spot. Add one line to the meta area: "Location: from the article, <place name>" when refined, otherwise "Location: approximate (country / region / city level)" from `location_confidence` (55 / 70 / 85). That is text only; no map restyling.
- Free and anonymous visitors never trigger the call; they just see the refined pin (and label) once the job or a premium user has refined it.

## 20.4 Tests and verification

- `tests/test_location_refine.py`: refined result persists with confidence 90; "none" persists and is never retried; transient failure is not persisted; country mismatch, country-only name and missing country are rejected; alias normaliser cases; non-GDELT skipped; already attempted makes zero external calls; lock prevents double refinement; `refine_pending` ordering, limit, early stop on repeated `unavailable`, `LOCATION_REFINE_PER_RUN=0` disables; `_upsert_crisis` keeps refined coordinates; endpoint 401 / 403 / 404 / 503 / 200 and the rate limit; `to_dict` fields. Existing real-headline tests updated.
- Live (scratch launcher, no product hooks): a fake AI client that returns a real place for a sample of Major events, with **real** Nominatim and real page fetches, to measure how many are accepted versus rejected by the country check and tune the alias table; confirm pins move on the globe, the stacked-pin counts drop, the Analysis line and recentring work, the premium on-open path works, and free/anonymous users trigger nothing.
- Backend suite, `tsc`, lint and build stay green.
- Owner: after deploy, set `ANTHROPIC_API_KEY` on Railway (optionally `ANTHROPIC_LOCATION_MODEL`, `LOCATION_REFINE_PER_RUN`) and spot-check a few refined events against their articles; run the Alembic migration on the production database.

## Out of scope

Country-level pins hidden or restyled by precision, precision circles around pins, ACLED coordinates, re-running refinement for events that previously found nothing, a paid geocoder (Nominatim's 1 request/second is plenty at this volume).

## Phase 20: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `backend/services/location_refine.py` (single-event refinement, country sanity check with an alias table, background `refine_pending`), migration `f3c9a1d7e502` (`location_refined_at`, `location_refined_name`), `POST /api/crises/<id>/refine-location` (premium, 20/min), scheduler job `location_refine` (every 20 min, `LOCATION_REFINE_PER_RUN`), `AI_LOCATION_MODEL` (Haiku) in `ai_client.py`, `NominatimGeocoder.geocode_status` and `extract_incident_location_status` (so an outage is retried instead of recorded as "nothing found"), sync no longer overwrites a refined pin; the refinement block was removed from `real-headline`. Frontend: `useRefineLocationMutation` (patches cached lists in place, no refetch), `EventAnalysis` asks once on open for premium and shows a location line for everyone. 721 backend tests pass (67 new); `tsc`, lint and build clean.

Verified live (real article fetches and real Nominatim; only the AI step stood in, since no key is set): a batch of 20 Major events gave 2 refined and 18 not (15 had no place from the crude stand-in's short list, 3 Nominatim no-match, none rejected for country or unreadable pages); opening an event as admin showed "Refining location from the article…", then "Location: from the article, Phoenix", moved the pin from the middle of Kansas to downtown Phoenix and recentred the camera; free users saw "Location: approximate (city level)" and sent no refinement requests; anonymous calls get 401.

Owner: set `ANTHROPIC_API_KEY` on Railway, run `alembic upgrade head` on the production database, and spot-check a few refined events against their articles; the real model's hit rate is not measured yet.

---

# Phase 21: Pins that mean what they say — statements vs places, precision, wider refinement, ACLED

## Context

Many pins sit nowhere near their event. Diagnosis from the live data (11,158 global GDELT events): **55% are statements** (CAMEO roots 10-13 and 16: demand, criticise, reject, threaten, reduce relations), which have no physical place, yet the feed gives them a point, usually where the actors or dateline are ("Trump rejects Iran's roadmap" lands in the US); **44% are physical** (arrest, fight, assault, protest, force) but 75% are at a city centre, 12% at a state centre, 13% at a country centre; and 5% of headlines name a different country than their pin. Decisions made with the owner: **A** statements are kept as pins but drawn differently (hollow, labelled "statement, approximate"); **B** refine every physical event, not only Major ones; **D** add ACLED (real incident coordinates); **E** show how precise each pin is. The cross-country check (C) was not chosen.

Findings from exploration:
- `GDELTConnector._parse_row` already has the CAMEO code (`event_root`, `_COL_EVENT_CODE`) and a precision signal (`location_confidence`: 55 country, 70 state, 85 city); `Crisis.analysis` for GDELT rows contains `CAMEO nnn`, so existing rows can be backfilled.
- CAMEO 17 (coerce) mixes arrests/seizures (physical) with administrative sanctions (code 172, not physical); every other root is clean.
- `ACLEDConnector` (`data_sources/acled.py`) is wired into sync but has **never run against a real account**: it needs `ACLED_EMAIL`/`ACLED_PASSWORD` (OAuth), its `ACLED_TYPE_MAP` keys include `'Battle'` where ACLED's value is `Battles` and non-ACLED names (`Cyber attack`, `Infrastructure attack`, `Displacement`), `location_confidence` is a flat 85 though ACLED returns `geo_precision` (1 exact, 2 near, 3 region), and **when unconfigured or on any error `fetch_recent_events` returns invented "sample" crises (`_get_sample_crises`) that sync saves to the database every hour** (the dev DB holds 7, e.g. "Kyiv Conflict Zone"), and `create_app` seeds the same samples into an empty database. That breaks the no-fabricated-data rule and is fixed here.
- ACLED data is free only for non-commercial use; a commercial product needs a licence. The connector stays off unless credentials are set, and the owner must confirm licensing before relying on it.
- `view=map` (`blueprints/crises.py`) builds the lean rows from column tuples; `test_crises_list_window.py` asserts the exact key set. The pin layer (`globe/crisisLayers.ts`) groups events by location; `Crisis.to_dict()` and `EventAnalysis.describeLocation` already carry the location text.

## 21.1 Backend: classify events and use ACLED's own precision

- `data_sources/constants.py`: `cameo_kind(code)` returns `'statement'` for roots 10, 11, 12, 13, 16 and for codes starting `172`, else `'physical'`; `None` for a missing/unparseable code. `GDELT_STATEMENT_ROOTS` documents the choice.
- Alembic migration (after `f3c9a1d7e502`): add `crises.event_kind` (String 12, null, indexed not needed). In the same migration, **backfill** GDELT rows in batches by parsing `CAMEO nnn` from `analysis` (self-contained copy of the rule), set `event_kind='physical'` for ACLED rows, and **deactivate** existing `source='Sample Data'` rows (`is_active=false`, rows kept).
- `GDELTConnector._parse_row`: set `event_kind = cameo_kind(event code)`. `ACLEDConnector._parse_event`: `event_kind='physical'`, `location_confidence` from `geo_precision` (1 → 92, 2 → 85, 3 → 70, missing → 85), fix the type map to ACLED's real values (`Battles`, `Violence against civilians`, `Explosions/Remote violence`, `Protests`, `Riots`, `Strategic developments`) and drop the invented ones; note in the docstring it is still unverified against a live account.
- Remove the sample fallbacks: `fetch_recent_events` returns `[]` (and logs) when unconfigured or on error; `create_app` no longer seeds samples into an empty database; `load_sample_data.py` stays as an explicit manual dev tool.
- `Crisis.to_dict()` adds `event_kind`. `view=map` adds `location_confidence` and `statement` (included only when true, to keep the payload small); update `LEAN_KEYS` tests.

## 21.2 Backend: refine every physical event (B)

- `services/location_refine.py`: `refine_pending` now selects GDELT, active, global scope, `event_kind = 'physical'`, `location_refined_at is null`, any severity (worst first, then newest) instead of Major only; `refine_crisis_location` returns `{'status': 'none', 'reason': 'statement'}` for a statement with no external call and without recording an attempt. Defaults stay (60 per 20 minutes is about 4,300 a day against roughly 700 new physical events a day).

## 21.3 Frontend: statements and precision on the map (A, E)

- `api/types.ts`: `CrisisSummary` gains `location_confidence` and `statement?`; `Crisis` gains `event_kind`. New `lib/precision.ts`: `precisionOf(confidence)` → `country` (<= 55), `region` (<= 70), `city` (< 90), `place` (>= 90), and `describePin(confidence, statement)` text shared by popups, the list and the Analysis line.
- `globe/crisisLayers.ts`: each location feature carries `statement` (true only when every event there is a statement) and `prec` (the lowest precision in the group). New halo layer under the pins: a translucent ring sized by precision (country largest, region medium, city small, place none). Pin layer: filled and white-edged for events that happened, **hollow with a coloured edge for statements**. Single-event popup and the stacked list rows gain the tags, e.g. "Statement, location approximate (country level)".
- New `globe/MapLegend.tsx` (Events mode only, bottom-left, compact on phones): filled = something that happened, hollow = a statement or talks, ring = approximate area (wider = less precise).
- `EventAnalysis.tsx`: for statements the location line reads "Statement or talks: the pin shows where the story is set, not where it happened"; the on-open refinement call skips statements. Existing refined/approximate wording stays for physical events.

## 21.4 Tests and verification

- Backend: `cameo_kind` table (each root, 172 vs other 17x, missing and malformed codes); `_parse_row` sets `event_kind`; ACLED `_parse_event` precision mapping and kind, type map, unconfigured/failed fetch returns `[]` (no sample rows); app start no longer seeds samples; migration backfill and sample deactivation run against a copy of the dev DB; lean view keys (`statement` only when true) and `to_dict`; `refine_pending` selection (physical, any severity, excludes statements, non-GDELT, refined, local, inactive) and the statement short-circuit. Update tests that relied on sample rows or on Major-only selection. Full suite stays green.
- Live (scratch launcher, as before): after migrating a copy of the dev DB, check the statement share matches the earlier analysis (about 55%), statements draw hollow and physical pins filled, halos grow with imprecision, popups and list rows carry the tags, the legend appears only in Events mode, the Analysis line for a statement, and that a premium open of a statement sends no refinement request; `tsc`, lint and build stay green.
- Owner: run `alembic upgrade head` in production (backfills `event_kind`, hides the sample rows); for ACLED, confirm commercial licensing, then set `ACLED_EMAIL` and `ACLED_PASSWORD` and check a first sync against the real feed (the connector has never run live).

## Out of scope

Hiding or filtering statements, per-country markers, country cross-checks, de-duplicating the same incident across GDELT and ACLED, a paid geocoder.

## Phase 21: ✅ IMPLEMENTED and verified (not yet committed or deployed)

New: `cameo_kind` and the statement/physical roots (`data_sources/gdelt.py`), `Crisis.event_kind`, migration `a5d8c2f1b934` (adds the column, backfills GDELT from `CAMEO nnn` in `analysis`, marks ACLED physical, hides the invented "Sample Data" rows), `statement` and `location_confidence` on the lean list, refinement now covers every unrefined physical GDELT event and skips statements, ACLED fixed (real type names, `geo_precision` to confidence, returns nothing when unconfigured or failing), no more invented sample events at sync or startup. Frontend: `lib/precision.ts`, hollow statement pins, precision halo layer, tags in single popups and stacked lists, `MapLegend` (Events mode; collapsed on phones), statement wording in the Analysis line, no refinement request for statements. 791 backend tests pass (70 new or updated); `tsc`, lint and build clean.

Verified live on the dev data: backfill gave 59% of global events as statements (all 576 sanctions codes statements, all 1,999 arrest codes physical), 15 sample rows hidden; the 48-hour list returns `statement` only on statements; statement pins draw hollow with rings, the key shows, a statement's popup and Analysis line carry the statement wording, phone layout fine. One real mistake found by a test and fixed: startup seeding was still running after my first edit.

Owner: run `alembic upgrade head` in production. ACLED: confirm commercial licensing, set `ACLED_EMAIL` and `ACLED_PASSWORD`, and check the first real sync (the connector has never run live). Refinement still needs `ANTHROPIC_API_KEY`.
