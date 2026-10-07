// Geodesic measuring for the drawing tool: distances, areas and the text shown on the map. Everything works on
// longitude and latitude on a sphere, never on screen pixels, so it is right on the globe and on the flat map. This
// file imports nothing so it can be unit-tested (frontend/tests/measure.test.ts).

export type Position = [number, number]; // [longitude, latitude] in degrees

export type UnitSystem = 'metric' | 'imperial';

const EARTH_RADIUS_M = 6371008.8; // the mean Earth radius
const rad = (deg: number) => (deg * Math.PI) / 180;

// Great-circle distance between two points, in metres (haversine).
export function distanceBetween(a: Position, b: Position): number {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function segmentLengths(coords: Position[]): number[] {
  const lengths: number[] = [];
  for (let i = 1; i < coords.length; i++) lengths.push(distanceBetween(coords[i - 1], coords[i]));
  return lengths;
}

// Length of a line (or the outline of a ring), in metres.
export function lineLength(coords: Position[]): number {
  return segmentLengths(coords).reduce((sum, n) => sum + n, 0);
}

function openRing(ring: Position[]): Position[] {
  const closed = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1];
  return closed ? ring.slice(0, -1) : ring;
}

// Area of one ring in square metres (spherical excess). The ring may or may not repeat its first point at the end.
export function ringArea(ring: Position[]): number {
  const points = openRing(ring);
  const n = points.length;
  if (n < 3) return 0;
  let total = 0;
  for (let i = 0; i < n; i++) {
    const before = points[(i + n - 1) % n];
    const here = points[i];
    const after = points[(i + 1) % n];
    total += (rad(after[0]) - rad(before[0])) * Math.sin(rad(here[1]));
  }
  return Math.abs((total * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

// Area of a polygon: the outer ring minus any holes, in square metres.
export function polygonArea(rings: Position[][]): number {
  if (rings.length === 0) return 0;
  const holes = rings.slice(1).reduce((sum, ring) => sum + ringArea(ring), 0);
  return Math.max(0, ringArea(rings[0]) - holes);
}

// Where to put a label for a line: the point a fraction of the way along it, by distance.
export function pointAlong(coords: Position[], fraction = 0.5): Position | null {
  if (coords.length === 0) return null;
  if (coords.length === 1) return coords[0];
  const lengths = segmentLengths(coords);
  const total = lengths.reduce((sum, n) => sum + n, 0);
  if (total === 0) return coords[0];
  let remaining = total * fraction;
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i] || i === lengths.length - 1) {
      const t = lengths[i] === 0 ? 0 : Math.min(1, remaining / lengths[i]);
      return [coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t];
    }
    remaining -= lengths[i];
  }
  return coords[coords.length - 1];
}

// Where to put a label for a polygon: the average of its corners (good enough for a label; not the true centroid).
export function ringCenter(ring: Position[]): Position | null {
  const points = openRing(ring);
  if (points.length === 0) return null;
  // Corners either side of the date line would average to the wrong side of the world, so shift them to one side first.
  const base = points[0][0];
  const lons = points.map((p) => {
    let lon = p[0];
    while (lon - base > 180) lon -= 360;
    while (lon - base < -180) lon += 360;
    return lon;
  });
  const lon = lons.reduce((s, n) => s + n, 0) / points.length;
  const lat = points.reduce((s, p) => s + p[1], 0) / points.length;
  return [((((lon + 180) % 360) + 360) % 360) - 180, lat];
}

const M_PER_FOOT = 0.3048;
const M_PER_MILE = 1609.344;
const SQ_M_PER_SQ_FOOT = M_PER_FOOT * M_PER_FOOT;
const SQ_M_PER_ACRE = 4046.8564224;
const SQ_M_PER_SQ_MILE = M_PER_MILE * M_PER_MILE;

// Whole numbers from 100 up (with thousands separators), one decimal from 10, two below that.
function fixed(value: number): string {
  if (value >= 100) return Math.round(value).toLocaleString('en-US');
  if (value >= 10) return value.toFixed(1).replace(/\.0$/, '');
  return value.toFixed(2).replace(/\.?0+$/, '');
}

// "850 m", "12.3 km", "420 ft", "3.1 mi"
export function formatDistance(metres: number, units: UnitSystem): string {
  if (!Number.isFinite(metres) || metres < 0) return '';
  if (units === 'imperial') {
    return metres < M_PER_MILE * 0.1
      ? `${Math.round(metres / M_PER_FOOT).toLocaleString('en-US')} ft`
      : `${fixed(metres / M_PER_MILE)} mi`;
  }
  return metres < 1000 ? `${Math.round(metres).toLocaleString('en-US')} m` : `${fixed(metres / 1000)} km`;
}

// "8,200 m²", "12.4 ha", "3.2 km²", "900 ft²", "14 acres", "5.1 mi²"
export function formatArea(squareMetres: number, units: UnitSystem): string {
  if (!Number.isFinite(squareMetres) || squareMetres < 0) return '';
  if (units === 'imperial') {
    if (squareMetres < SQ_M_PER_ACRE * 0.25) return `${Math.round(squareMetres / SQ_M_PER_SQ_FOOT).toLocaleString('en-US')} ft²`;
    if (squareMetres < SQ_M_PER_SQ_MILE * 0.25) return `${fixed(squareMetres / SQ_M_PER_ACRE)} acres`;
    return `${fixed(squareMetres / SQ_M_PER_SQ_MILE)} mi²`;
  }
  if (squareMetres < 10_000) return `${Math.round(squareMetres).toLocaleString('en-US')} m²`;
  if (squareMetres < 1_000_000) return `${fixed(squareMetres / 10_000)} ha`;
  return `${fixed(squareMetres / 1_000_000)} km²`;
}

// A shape that has only just been started (a circle with no radius yet, a line with one corner) has no size worth showing.
const MIN_LABEL_LENGTH_M = 1;
const MIN_LABEL_AREA_M2 = 1;

export interface MapLabel {
  id: string;
  position: Position;
  text: string;
}

// The label for each drawn shape: a line shows its length, a polygon (rectangles and circles included) its area and
// perimeter. Points have none. `features` are GeoJSON features as the drawing engine stores them.
export function labelsFor(
  features: { id?: string | number; geometry: { type: string; coordinates: unknown } }[],
  units: UnitSystem,
): MapLabel[] {
  const labels: MapLabel[] = [];
  for (const feature of features) {
    const id = String(feature.id ?? '');
    if (feature.geometry.type === 'LineString') {
      const coords = feature.geometry.coordinates as Position[];
      if (coords.length < 2) continue;
      const at = pointAlong(coords);
      const length = lineLength(coords);
      if (at && length >= MIN_LABEL_LENGTH_M) labels.push({ id, position: at, text: formatDistance(length, units) });
    } else if (feature.geometry.type === 'Polygon') {
      const rings = feature.geometry.coordinates as Position[][];
      if (!rings[0] || rings[0].length < 4) continue;
      const at = ringCenter(rings[0]);
      const area = polygonArea(rings);
      if (at && area >= MIN_LABEL_AREA_M2) {
        labels.push({ id, position: at, text: `${formatArea(area, units)}\n${formatDistance(lineLength(rings[0]), units)} around` });
      }
    }
  }
  return labels;
}
