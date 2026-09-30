import * as maplibregl from 'maplibre-gl';

// Real timezone boundary data — NOT live-fetched (boundaries change
// extremely rarely, per the rewrite plan), served as a static file from
// Vite's `public/` dir (frontend/public/timezones.geojson) since MapLibre
// can add a GeoJSON source straight from a static URL with no backend
// involvement at all.
//
// Source: timezone-boundary-builder (https://github.com/evansiroky/timezone-boundary-builder),
// release 2026d, the "timezones-now.geojson.zip" asset — real IANA tzdata
// political boundaries built from OpenStreetMap data (ODbL license). This
// is the project's own officially-published *reduced* variant: it merges
// zones that currently share identical UTC offset/DST rules (65 polygons
// covering the whole world) rather than the full ~450-zone historical set,
// which is exactly right here since we only ever display *current* local
// time. The polygon geometry was further simplified with `mapshaper`
// (-simplify 5% -clean) to shrink it from the raw 81MB download to ~2.4MB
// for a reasonable repo footprint — geometry simplification only, no
// boundary data was invented; the `tzid` values (real IANA zone names,
// e.g. "Asia/Tokyo") are untouched.
const TIMEZONE_GEOJSON_URL = '/timezones.geojson';
const SOURCE_ID = 'timezone-boundaries';
const LINE_LAYER_ID = 'timezone-boundaries-line';
const FILL_LAYER_ID = 'timezone-boundaries-hit';

export function addTimezoneLayer(map: maplibregl.Map) {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, {
    type: 'geojson',
    data: TIMEZONE_GEOJSON_URL,
  });

  // Invisible fill layer purely for click hit-testing (same pattern as
  // Globe.tsx's country hit-test layer) — the boundary lines themselves
  // are too thin to reliably click.
  map.addLayer({
    id: FILL_LAYER_ID,
    type: 'fill',
    source: SOURCE_ID,
    paint: { 'fill-color': '#000000', 'fill-opacity': 0 },
  });

  map.addLayer({
    id: LINE_LAYER_ID,
    type: 'line',
    source: SOURCE_ID,
    paint: {
      'line-color': '#5aa0ff',
      'line-width': 1,
      'line-opacity': 0.6,
    },
  });
}

export function removeTimezoneLayer(map: maplibregl.Map) {
  if (map.getLayer(LINE_LAYER_ID)) map.removeLayer(LINE_LAYER_ID);
  if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID);
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
}

// Real current local time for a real IANA zone name, computed entirely
// client-side via the browser's native Intl API — no backend endpoint or
// live API call, per the plan's explicit instruction (zero rate-limit
// risk, always accurate, and trivially correct for DST since Intl/ICU
// carries the full tzdata rules the browser ships with).
export function currentTimeForZone(tzid: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: tzid,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    }).format(new Date());
  } catch {
    return 'unknown';
  }
}

export function timezonePopupHtml(tzid: string): string {
  const div = document.createElement('div');
  div.textContent = tzid;
  const safeTzid = div.innerHTML;
  return `<strong>${safeTzid}</strong><br/>${currentTimeForZone(tzid)}`;
}

export const TIMEZONE_HIT_LAYER_ID = FILL_LAYER_ID;
