"""
GDACS (Global Disaster Alert and Coordination System, gdacs.org) connector —
real, free, no-key GeoJSON feed of currently active global disasters, used
here for the Weather mode's catastrophic-storm pins (step 5 of the rewrite
plan).

Live-verified at implementation time (2026-09-29): the "EVENTS4APP" GeoJSON
endpoint (the one GDACS's own web app/map uses) is reachable without any
key or registration and returns a FeatureCollection of ~100 currently
active/recent events across ALL disaster types it tracks (earthquakes,
floods, wildfires, tropical cyclones, etc) — e.g.:

    GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP

Each feature's `properties.eventtype` is a two-letter code (`TC` = Tropical
Cyclone, `EQ` = Earthquake, `FL` = Flood, `WF` = Wildfire, `DR` = Drought,
`VO` = Volcano, `TS` = Tsunami). The `eventlist=TC` query param that GDACS's
own docs suggest for server-side filtering was tried live and does NOT
actually filter the response (confirmed: passing `eventlist=TC` still
returned EQ/WF/FL/TC events mixed together) — so filtering is done
client-side here instead, which is more robust anyway (not dependent on an
undocumented/broken query param).

Per this plan's explicit scope ("catastrophic storms" specifically, not
every GDACS disaster type), this connector filters to `eventtype == 'TC'`
(tropical cyclones) only — not earthquakes/volcanoes/wildfires, which
aren't weather. Each feature also carries a real `severitydata` block (peak
wind speed in km/h and a human-readable category string) and an
`alertlevel` (Green/Orange/Red, GDACS's own severity classification), both
parsed through as real fields rather than invented.

Returns [] (not None) when the live feed has zero current tropical
cyclones — a legitimate real state, not an error — and returns None only
when the feed itself could not be fetched/parsed, so the blueprint can
distinguish "genuinely no storms right now" from "GDACS is unreachable".
"""
import logging

try:
    import requests
except Exception:
    requests = None

logger = logging.getLogger(__name__)

GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

# The only eventtype this connector surfaces — tropical cyclones. GDACS
# tracks other disaster types (EQ, FL, WF, DR, VO, TS) but the plan's
# explicit ask is catastrophic *storms*, not every hazard category.
_STORM_EVENT_TYPES = {'TC'}


class GDACSConnector:
    """Fetch real, currently active tropical-cyclone alerts from GDACS."""

    @staticmethod
    def fetch_active_storms():
        """
        Returns a list of real storm dicts (possibly empty if there are
        genuinely no active tropical cyclones right now) on success, or
        None if the live GDACS feed itself is unreachable/unparseable —
        never a fabricated storm.
        """
        if not requests:
            return None

        try:
            resp = requests.get(GDACS_EVENTS_URL, timeout=8)
            if resp.status_code != 200:
                logger.info(f"[GDACS] HTTP {resp.status_code}, unavailable (no fallback fabrication)")
                return None

            payload = resp.json()
            features = payload.get('features') or []

            storms = []
            for feature in features:
                props = feature.get('properties') or {}
                if props.get('eventtype') not in _STORM_EVENT_TYPES:
                    continue

                geometry = feature.get('geometry') or {}
                coords = geometry.get('coordinates')
                lon, lat = (coords[0], coords[1]) if coords and len(coords) >= 2 else (None, None)

                severity = props.get('severitydata') or {}
                urls = props.get('url') or {}

                storms.append({
                    'id': props.get('eventid'),
                    'name': props.get('eventname') or props.get('name'),
                    'event_type': props.get('eventtype'),
                    'lat': lat,
                    'lon': lon,
                    'alert_level': props.get('alertlevel'),
                    'severity_kmh': severity.get('severity'),
                    'severity_text': severity.get('severitytext'),
                    'country': props.get('country'),
                    'from_date': props.get('fromdate'),
                    'to_date': props.get('todate'),
                    'date_modified': props.get('datemodified'),
                    'report_url': urls.get('report'),
                    'source': 'gdacs.org',
                })

            return storms
        except Exception as e:
            logger.info(f"[GDACS] fetch failed: {e}")
            return None
