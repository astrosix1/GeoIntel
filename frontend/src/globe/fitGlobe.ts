import type * as maplibregl from 'maplibre-gl';

// How much of the map area's smaller side the globe should fill when it is first shown (and when the panels around it
// open or close), until the user zooms for themselves.
const FILL = 0.88;
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 3.4;

// The globe's pixel width at a zoom: the distance between two points on its opposite edges, measured with the map's own
// projection so it stays right whatever the projection code does with perspective.
function globeWidth(map: maplibregl.Map, zoom: number): number {
  map.jumpTo({ zoom, center: [0, 0] });
  const a = map.project([89, 0]);
  const b = map.project([-89, 0]);
  return Math.hypot(a.x - b.x, a.y - b.y);
}

// Sets the zoom so the whole globe fits the map's box with a little air around it, keeping the current centre.
export function fitGlobe(map: maplibregl.Map): void {
  const box = map.getContainer().getBoundingClientRect();
  const target = FILL * Math.min(box.width, box.height);
  if (!(target > 50)) return;
  const center = map.getCenter();
  const bearing = map.getBearing();
  const pitch = map.getPitch();
  let lo = MIN_ZOOM;
  let hi = MAX_ZOOM;
  for (let i = 0; i < 12; i++) {
    const mid = (lo + hi) / 2;
    if (globeWidth(map, mid) < target) lo = mid;
    else hi = mid;
  }
  map.jumpTo({ zoom: (lo + hi) / 2, center, bearing, pitch });
}

// The flat (Mercator) map: the zoom at which the whole world, from 70 degrees north to 58 south, fits the box. A
// Mercator world is 512 px wide at zoom 0 and doubles with each zoom level.
const FLAT_FILL = 0.98;
const FLAT_SPAN = 0.552; // the share of the world's width that 70 N to 58 S takes up vertically
export const FLAT_CENTER: [number, number] = [0, 12];

export function flatZoomFor(width: number, height: number): number {
  const fit = Math.min(width, height / FLAT_SPAN) * FLAT_FILL;
  return Math.log2(Math.max(fit, 1) / 512);
}

export function fitFlat(map: maplibregl.Map): void {
  const box = map.getContainer().getBoundingClientRect();
  if (!(box.width > 50 && box.height > 50)) return;
  map.jumpTo({ zoom: flatZoomFor(box.width, box.height), center: FLAT_CENTER, bearing: 0, pitch: 0 });
}
