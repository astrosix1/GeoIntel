import * as maplibregl from 'maplibre-gl';

// Weather radar from RainViewer: a global mosaic of real weather-radar
// reflectivity, published as one tile set per ~10-minute frame (about two
// hours of history). Each frame is its own raster layer; the visible one is
// switched by opacity so every frame stays preloaded and the loop doesn't
// flicker.

export interface RadarFrame {
  time: number; // unix seconds
  path: string; // e.g. /v2/radar/ffee53cec31b
}

export interface RadarWant {
  host: string;
  frames: RadarFrame[];
  index: number; // which frame is visible
}

const SOURCE_PREFIX = 'radar-src-';
const LAYER_PREFIX = 'radar-layer-';
const RADAR_OPACITY = 0.75;

// RainViewer colour scheme 4 (green -> yellow -> red) reads clearly over both
// the blue oceans and the land fill; "1_1" = smoothed, with snow shown.
const COLOR_AND_OPTIONS = '4/1_1';

// RainViewer rate-limits each IP (500 requests/minute, burst 300), and every
// preloaded frame requests its own tiles. 512 px tiles cover four times the
// area of 256 px ones, so a view needs about a quarter of the requests; radar
// resolution is coarse enough that nothing visible is lost. Native zoom for
// free 512 px tiles tops out at 6 (7 for 256 px); MapLibre overzooms beyond.
const TILE_SIZE = 512;
const MAX_NATIVE_ZOOM = 6;

const ATTRIBUTION =
  'Radar: <a href="https://www.rainviewer.com/" target="_blank" rel="noopener noreferrer">RainViewer</a>';

function radarLayerIds(map: maplibregl.Map): string[] {
  return map
    .getStyle()
    .layers.map((l) => l.id)
    .filter((id) => id.startsWith(LAYER_PREFIX));
}

export function removeRadar(map: maplibregl.Map): void {
  radarLayerIds(map).forEach((id) => map.removeLayer(id));
  Object.keys(map.getStyle().sources ?? {})
    .filter((id) => id.startsWith(SOURCE_PREFIX))
    .forEach((id) => map.removeSource(id));
}

// Makes the map match `want` (null = no radar). Idempotent, so it can run on
// every frame change: it only adds frames it doesn't have yet and flips opacity.
export function syncRadar(map: maplibregl.Map, want: RadarWant | null): void {
  if (!want || want.frames.length === 0) {
    removeRadar(map);
    return;
  }

  const wanted = new Set(want.frames.map((f) => String(f.time)));

  // Drop frames that have aged out of the feed.
  radarLayerIds(map).forEach((id) => {
    const time = id.slice(LAYER_PREFIX.length);
    if (!wanted.has(time)) {
      map.removeLayer(id);
      if (map.getSource(SOURCE_PREFIX + time)) map.removeSource(SOURCE_PREFIX + time);
    }
  });

  // Above the land fills and any satellite/relief, below borders and labels.
  const anchor = map.getStyle().layers.find((l) => l.id.startsWith('boundary_'))?.id;

  want.frames.forEach((frame, i) => {
    const key = String(frame.time);
    if (!map.getSource(SOURCE_PREFIX + key)) {
      map.addSource(SOURCE_PREFIX + key, {
        type: 'raster',
        tiles: [`${want.host}${frame.path}/${TILE_SIZE}/{z}/{x}/{y}/${COLOR_AND_OPTIONS}.png`],
        tileSize: TILE_SIZE,
        maxzoom: MAX_NATIVE_ZOOM,
        attribution: ATTRIBUTION,
      });
    }
    if (!map.getLayer(LAYER_PREFIX + key)) {
      map.addLayer(
        {
          id: LAYER_PREFIX + key,
          type: 'raster',
          source: SOURCE_PREFIX + key,
          paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-opacity-transition': { duration: 0 } },
        },
        anchor,
      );
    }
    map.setPaintProperty(LAYER_PREFIX + key, 'raster-opacity', i === want.index ? RADAR_OPACITY : 0);
  });
}
