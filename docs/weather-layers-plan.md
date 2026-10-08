# Weather layers and air quality

Plan for the two items left over from `docs/weather-mode-plan.md` (stage 4): extra map layers (wind, temperature, cloud, pressure) and air-quality alerts. Both were blocked on one question: which data sources may a **paid, subscription product** use? This plan answers that with checks made on 2026-10-08. Nothing here is built yet.

## A compliance finding that comes first

**Open-Meteo's free API is for non-commercial use only**, and its terms name our case: "Operating websites or apps that have subscriptions or display advertisements" counts as commercial use. GeoIntel has a premium subscription. Today Open-Meteo feeds:

- the point forecast panel (`services/forecast.py`),
- Compare places,
- the forecast-limit alerts (`services/condition_alerts.py`, up to 400 forecasts an hour),
- and would feed air quality.

Open-Meteo sells a commercial licence (Standard plan, 1 million calls a month; the price is on its pricing page) that grants a key and a dedicated endpoint. Everything else about the integration would stay the same. The alternative is to move forecasts to a source that allows commercial use.

This is the same kind of question that was settled for RainViewer earlier, so it needs a decision before any new weather feature ships on top of Open-Meteo.

## What was checked (live, no key)

| Source | Works | Terms (as read) | What it gives |
|---|---|---|---|
| **DWD ICON global, WMS** (`maps.dwd.de/geoserver/dwd/wms`) | yes: a 512 px temperature map came back | German open-data licence (GeoNutzV): free including commercial use, with a source line. **The official wording still has to be read and quoted before shipping** (the English and German terms pages returned 404 from here). | Global forecast layers on a 0.25 degree grid: 2 m temperature, sea-level pressure, 10 m wind, accumulated rain (6, 12, 24 h). Temperature and pressure have a **hourly time axis, about 9 days** (2026-10-07 to 10-16). Wind has no time axis in the capabilities and needs a closer look. No cloud layer in the global set. |
| **NASA GIBS** (WMTS, keyless) | yes: 5.8 MB capabilities read | NASA data, no restrictions; credit NASA GIBS | **Observed**, not forecast: true-colour satellite (clouds are visible in it), IMERG rain rate, active-fire detections (VIIRS), aerosol and nitrogen-dioxide columns, snow cover, sea-surface temperature and ocean wind. Delays from 30 minutes to a day. No "current" wind, temperature or pressure. |
| **MET Norway Locationforecast** | yes: 87 hourly steps | Free including commercial use, with a User-Agent that names the app, attribution, caching and a request cap | Point forecast: temperature, pressure, cloud, humidity, wind. A possible replacement for Open-Meteo's forecast. No air quality outside Norway. |
| **Open-Meteo** | yes | Free tier non-commercial only (above); commercial plan available | Forecast, plus the Air Quality API (CAMS model data). |
| OpenWeatherMap tiles | not probed | Needs a key; free plan call limits count every tile | Skip: tile requests burn the daily quota. |
| RainViewer | in use | Settled earlier | Radar (observed). |

## What this means for each layer

| Layer | Source | Kind | Time control |
|---|---|---|---|
| Temperature | DWD ICON | forecast | existing time bar, hourly |
| Pressure | DWD ICON | forecast | same |
| Rain forecast | DWD ICON (6 h totals) | forecast | same |
| Wind | DWD ICON 10 m wind (barbs or colour) | forecast | same, if it has a time axis; otherwise the latest only |
| Clouds | NASA GIBS true colour (clouds visible) | observed, yesterday's composite | date picker |
| Fires | NASA GIBS VIIRS thermal anomalies | observed, about 3 hours old | last 24 h |
| Air quality (map) | NASA GIBS nitrogen-dioxide and aerosol columns | observed columns, not ground-level readings | date picker |

Every layer says whether it is **forecast or observed** and how old it is, in the layer menu and on the time bar (the existing rule: "say how old it is, real data only"). Cloud, fire and air-quality layers are satellite observations and are labelled as such: they are not a ground-level air-quality index.

## Air quality alerts

A ground-level air-quality index (PM2.5, ozone, nitrogen dioxide, US or EU AQI) with a forecast comes from the CAMS atmosphere model. The only keyless route is the Open-Meteo Air Quality API, which is covered by the commercial question above. Alternatives are the Copernicus Atmosphere Data Store (free key, data licence allows commercial use, but heavy gridded files) or OpenAQ (free key, ground stations, licences vary by station). **The simple, honest path is the Open-Meteo commercial plan.** Without it, air quality stays satellite-only on the map and has no alerts.

## Decisions needed

1. **Open-Meteo.** (a) Buy the commercial plan: smallest change, covers forecast, alerts and air quality. (b) Move forecasts and alerts to MET Norway (free, commercial-allowed, a few days of work, including turning its hourly data into the daily figures the alerts use), and leave air-quality alerts out. (c) Leave it as is and accept the licence risk. Recommended: **(a)** if the cost is acceptable, otherwise (b). Not (c).
2. **First set of layers.** Temperature, pressure, rain forecast and wind from DWD, plus clouds and fires from NASA. Add or drop any?
3. **DWD terms.** I will quote the licence from DWD's own page before shipping; if I cannot confirm commercial use, the four DWD layers do not ship and temperature, pressure and wind fall back to GIBS observations only.

## Stages (after the decisions)

0. **Terms and plumbing.** Confirm and record each source's terms in this file. A layer registry (id, label, kind forecast or observed, source, attribution, time support) replaces the hard-coded radar entry in `LayersMenu` and `baseLayers`, with a visible attribution line for every active layer.
1. **DWD layers** as raster sources driven by the existing time bar, with legends (temperature scale, pressure, wind speed, rain). Check the tile projection against the globe and flat map.
2. **NASA layers** (clouds, fires, air-quality columns) with a date control and age labels.
3. **Forecast provider** (if decision 1 is (a): key and endpoint switch, no behaviour change; if (b): MET Norway adapter and daily aggregation behind the same `get_forecast`).
4. **Air-quality alerts** (only with the commercial plan): AQI limits in Dashboard > Alerts next to heat, cold, rain, gusts and UV, same per-place, same dedupe; Supabase column for the limits.
5. **Polish:** layer legends and ages on mobile, keyboard access, a test per layer source (capabilities, time extent, error state).

## Risks

- **Licence wording** for DWD must be read in full (see decision 3).
- **DWD tile reprojection:** the server answered a world map request in a way that suggests it stretches data rather than reprojecting; the layers may need to be requested in lat/lon tiles and warped client-side, or fetched as a single image per time step.
- **Load:** hourly time steps for four layers means many tiles; time steps are fetched only for the visible window and cached by the browser.
- **GIBS delays:** observed layers can be a day old; the labels must say so.
- **Open-Meteo cost** if decision 1 is (a).

## Decisions (made by the owner, 2026-10-08)

1. **Open-Meteo: option (b).** Forecasts, Compare places and the forecast-limit alerts move to MET Norway. Air-quality alerts are left out. 
2. **First layer set:** DWD temperature, pressure, rain forecast and wind; NASA clouds and fires.
3. **DWD terms confirmed** from DWD's own legal notice (dwd.de, "Rechtliche Hinweise"): all freely accessible geodata and geodata services, which it says include all weather and climate information with a place reference, may be reused under **CC BY 4.0 with a source line**, which permits commercial use. Source line: "Quelle: Deutscher Wetterdienst". So the DWD layers can ship.
4. **MET Norway terms confirmed** (api.met.no/doc/TermsOfService and /License): NLOD 2.0 / CC BY 4.0, attribution required; identify the app in the User-Agent; truncate coordinates to 4 decimals; cache and use If-Modified-Since; under 20 requests a second; call it from a backend proxy.

## Stage 3 first: the forecast provider (as built; done before the layers because it is the live licence issue)

- **`services/forecast_met.py`** builds the existing forecast shape from MET Norway Locationforecast (complete), so the panels, Compare places and the alert job needed no change. `services/forecast.py` picks the provider: **MET Norway by default, Open-Meteo only when `OPEN_METEO_API_KEY` is set** (the commercial plan; the code for that already existed). Setting that key later restores the fields below with no code change.
- **Times:** MET speaks UTC, so `services/timezone_lookup.py` (a point-in-polygon lookup over `backend/data/timezones.geojson`, the map's own zone file) gives each place its zone, and the forecast keeps showing the place's local clock with days cut at local midnight. `tzdata` was added to the requirements.
- **What MET Norway does not give for a global point** (checked against live responses): wind gusts, chance of rain, visibility, and the UV index beyond about 2.7 days (and it is the clear-sky value). These are returned as missing, never estimated. Feels-like, humidity, pressure, cloud, hourly rain (6-hourly after about 2.7 days, shown as an average per hour), a weather symbol (mapped to the same icons) and nine days of steps are available. There is no "last 24 hours" series, so that panel is empty.
- **Alerts:** the strong-gusts limit is no longer offered (the settings screen says why), and the UV limit looks at the next two days. A missing value never fires an alert.
- **Place search** moved from Open-Meteo's geocoder to OpenStreetMap's Nominatim (searches on submit, results cached, "© OpenStreetMap contributors" shown), again unless the Open-Meteo key is set.
- **Respecting MET's rules:** a User-Agent naming the app (`MET_USER_AGENT` can override it), coordinates rounded to 0.1 degree, a 10-minute freshness window then `If-Modified-Since` revalidation, a stale copy up to 3 hours old if MET is down (its real age is shown), and the attribution on every forecast panel.
- Tested: 25 new tests plus the existing ones (1,269 in all) and the browser (Tokyo: local time, feels-like, hourly and 7-day panels, attribution and the "no gusts" note).

## Stages 0 to 2 as built (the layers)

- **Backend:** `data_sources/dwd.py` reads DWD's WMS capabilities (cached 30 minutes) and `GET /api/weather/layers` returns, for each forecast layer, the exact hours the service can draw (temperature and pressure hourly, wind hourly for three days then three-hourly, rain every three hours; about nine days). A layer whose hours cannot be read is left out, so the app never offers a layer it cannot draw. Source line and licence are returned with it.
- **Forecast map (DWD ICON, one at a time):** temperature (2 m), sea-level pressure (isobars with labels), rain over the six hours to the chosen time, wind (barbs, white on satellite imagery so they stay visible). Drawn as raster tiles straight from DWD; the browser asks DWD, not our server. A **forecast bar** under the map (above the radar bar when both show) steps through every available hour, says "model, not observed", and has a **Now** button. A **legend** (DWD's own colour key, or a plain explanation of wind barbs) sits top left of the map.
- **Satellite overlays (NASA GIBS):** **cloud cover**, the previous day's MODIS daily composite (it has gaps between satellite passes, and the menu says so), and **fires**, VIIRS detections for today so far. GIBS publishes fires only as vector data, so they are drawn through its WMS as transparent dots.
- **Layers menu** (Weather mode): radar, cloud cover and fires switches, and a "Forecast map (model, not observed)" group of radio buttons. Attributions are on the map's attribution control (DWD with its CC BY 4.0 line, NASA GIBS).
- **Care taken:** a forecast hour is only ever one the chosen layer has (each layer has its own hours; DWD answers a wrong hour with an error, not a picture), dragging the bar is smoothed so each pause draws one set of tiles, layers are put back after a base-map change, and the layers sit under the radar and above the land.
- **Not built:** air-quality map columns (NASA nitrogen dioxide and aerosol layers) were left out of this first set, and air-quality alerts stay out (decision 1).
- **Checked in the browser:** each of the four forecast fields and both satellite overlays, the time slider, switching between layers, and the legends.
