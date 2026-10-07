// Geodesic measuring for the drawing tool: distances, areas, bearings, angles and the text shown on the map. Everything
// works on longitude and latitude on a sphere, never on screen pixels, so it is right on the globe and on the flat map.
// This file imports nothing so it can be unit-tested (frontend/tests/measure.test.ts).

export type Position = [number, number]; // [longitude, latitude] in degrees

// Nautical uses nautical miles for distance and the metric units for area.
export type UnitSystem = 'metric' | 'imperial' | 'nautical';

const EARTH_RADIUS_M = 6371008.8; // the mean Earth radius
const rad = (deg: number) => (deg * Math.PI) / 180;
const deg = (radians: number) => (radians * 180) / Math.PI;

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

// Makes a run of points continuous across the date line: each longitude is shifted by whole turns so it is within half a turn
// of the one before it (179 then -179 becomes 179 then 181). A shape drawn across the date line can arrive either way, with
// longitudes that run on past 180 or that wrap round, and the area and label maths needs the continuous form.
export function unwrapLongitudes(coords: Position[]): Position[] {
  const out: Position[] = [];
  for (const [lon, lat] of coords) {
    let value = lon;
    if (out.length > 0) {
      const previous = out[out.length - 1][0];
      while (value - previous > 180) value -= 360;
      while (value - previous < -180) value += 360;
    }
    out.push([value, lat]);
  }
  return out;
}

function openRing(ring: Position[]): Position[] {
  // Closed when the last point repeats the first (within floating-point noise).
  const last = ring[ring.length - 1];
  const closed = ring.length > 1 && Math.abs(ring[0][0] - last[0]) < 1e-9 && Math.abs(ring[0][1] - last[1]) < 1e-9;
  return closed ? ring.slice(0, -1) : ring;
}

// Area of one ring in square metres (spherical excess). The ring may or may not repeat its first point at the end.
export function ringArea(ring: Position[]): number {
  const points = unwrapLongitudes(openRing(ring));
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
export function pointAlong(path: Position[], fraction = 0.5): Position | null {
  const coords = unwrapLongitudes(path);
  if (coords.length === 0) return null;
  if (coords.length === 1) return coords[0];
  const lengths = segmentLengths(coords);
  const total = lengths.reduce((sum, n) => sum + n, 0);
  if (total === 0) return coords[0];
  let remaining = total * fraction;
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i] || i === lengths.length - 1) {
      const t = lengths[i] === 0 ? 0 : Math.min(1, remaining / lengths[i]);
      const lon = coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t;
      return [((((lon + 180) % 360) + 360) % 360) - 180, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t];
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

// ---- Directions and angles -----------------------------------------------------------------------------------------------

// The initial compass bearing from one point to another, in degrees clockwise from north (0 to 360).
export function bearingBetween(a: Position, b: Position): number {
  const lat1 = rad(a[1]);
  const lat2 = rad(b[1]);
  const dLon = rad(b[0] - a[0]);
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

export function compassPoint(degrees: number): string {
  return COMPASS[Math.round((((degrees % 360) + 360) % 360) / 45) % 8];
}

// "047° NE"
export function formatBearing(degrees: number): string {
  const whole = Math.round(((degrees % 360) + 360) % 360) % 360;
  return `${String(whole).padStart(3, '0')}° ${compassPoint(whole)}`;
}

// The angle at `vertex` between the lines to `from` and to `to`, in degrees from 0 to 180 (the smaller of the two angles
// the lines make; a reflex corner of a polygon therefore reads as its smaller supplement).
export function angleAt(from: Position, vertex: Position, to: Position): number {
  const diff = Math.abs(bearingBetween(vertex, from) - bearingBetween(vertex, to));
  return diff > 180 ? 360 - diff : diff;
}

export function formatAngle(degrees: number): string {
  return `${Math.round(degrees * 10) / 10}°`;
}

// The point halfway between two points along the great circle (not the average of the numbers, which is wrong far from
// the equator and across the date line).
export function midpointBetween(a: Position, b: Position): Position {
  const lat1 = rad(a[1]);
  const lon1 = rad(a[0]);
  const lat2 = rad(b[1]);
  const dLon = rad(b[0] - a[0]);
  const bx = Math.cos(lat2) * Math.cos(dLon);
  const by = Math.cos(lat2) * Math.sin(dLon);
  const lat = Math.atan2(Math.sin(lat1) + Math.sin(lat2), Math.sqrt((Math.cos(lat1) + bx) ** 2 + by ** 2));
  const lon = lon1 + Math.atan2(by, Math.cos(lat1) + bx);
  return [((((deg(lon) + 180) % 360) + 360) % 360) - 180, deg(lat)];
}

// "51.5074° N, 0.1278° W"
export function formatCoordinates(position: Position): string {
  const [lon, lat] = position;
  const part = (value: number, positive: string, negative: string) => `${Math.abs(value).toFixed(4)}° ${value >= 0 ? positive : negative}`;
  return `${part(lat, 'N', 'S')}, ${part(lon, 'E', 'W')}`;
}

// ---- Units ---------------------------------------------------------------------------------------------------------------------

const M_PER_FOOT = 0.3048;
const M_PER_MILE = 1609.344;
const M_PER_NAUTICAL_MILE = 1852;
const SQ_M_PER_SQ_FOOT = M_PER_FOOT * M_PER_FOOT;
const SQ_M_PER_ACRE = 4046.8564224;
const SQ_M_PER_SQ_MILE = M_PER_MILE * M_PER_MILE;

// Whole numbers from 100 up (with thousands separators), one decimal from 10, two below that.
function fixed(value: number): string {
  if (value >= 100) return Math.round(value).toLocaleString('en-US');
  if (value >= 10) return value.toFixed(1).replace(/\.0$/, '');
  return value.toFixed(2).replace(/\.?0+$/, '');
}

// "850 m", "12.3 km", "420 ft", "3.1 mi", "6.7 nm"
export function formatDistance(metres: number, units: UnitSystem): string {
  if (!Number.isFinite(metres) || metres < 0) return '';
  if (units === 'nautical') {
    return metres < M_PER_NAUTICAL_MILE * 0.1
      ? `${Math.round(metres).toLocaleString('en-US')} m`
      : `${fixed(metres / M_PER_NAUTICAL_MILE)} nm`;
  }
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

// ---- Map labels ------------------------------------------------------------------------------------------------------------------

// name: the user's own name for a shape; text: a text label drawn with the Text tool (the whole shape is the text).
export type LabelKind = 'total' | 'segment' | 'angle' | 'point' | 'name' | 'text';

export interface MapLabel {
  id: string;
  kind: LabelKind;
  position: Position;
  text: string;
  color?: string; // the shape's colour, used for the Text tool's text
}

export interface LabelOptions {
  units: UnitSystem;
  segments: boolean; // the length of every segment, not just the total
  angles: boolean; // the angle at every corner
  bearings: boolean; // the compass bearing of every segment
}

export interface LabelFeature {
  id?: string | number;
  geometry: { type: string; coordinates: unknown };
  properties?: Record<string, unknown> | null;
}

// A shape that has only just been started (a circle with no radius yet, a line with one corner) has no size worth showing.
const MIN_LABEL_LENGTH_M = 1;
const MIN_LABEL_AREA_M2 = 1;
// A polygon with more corners than this gets its total only: a label on every side would bury the map.
const MAX_LABELLED_CORNERS = 12;

function segmentText(a: Position, b: Position, options: LabelOptions, forceLength: boolean): string {
  const parts: string[] = [];
  if (options.segments || forceLength) parts.push(formatDistance(distanceBetween(a, b), options.units));
  if (options.bearings) parts.push(formatBearing(bearingBetween(a, b)));
  return parts.join(' · ');
}

function segmentLabels(id: string, coords: Position[], options: LabelOptions, forceLength: boolean, labels: MapLabel[]): void {
  for (let i = 1; i < coords.length; i++) {
    const text = segmentText(coords[i - 1], coords[i], options, forceLength);
    if (text && distanceBetween(coords[i - 1], coords[i]) >= MIN_LABEL_LENGTH_M) {
      labels.push({ id, kind: 'segment', position: midpointBetween(coords[i - 1], coords[i]), text });
    }
  }
}

// The labels for each drawn shape.
// - A line: its total length (and, when asked, each segment's length and bearing and the angle at each inner corner).
// - An angle (three corners): the angle at the middle corner and the length of both legs, always.
// - A polygon (rectangles too): area and perimeter, and when asked each side and each corner's angle.
// - A circle: radius, area and circumference.
// - A point: its coordinates.
// `features` are GeoJSON features as the drawing engine stores them.
export function labelsFor(features: LabelFeature[], options: LabelOptions): MapLabel[] {
  const labels: MapLabel[] = [];
  const { units } = options;
  for (const feature of features) {
    const id = String(feature.id ?? '');
    const mode = feature.properties?.mode;
    const type = feature.geometry.type;

    const name = typeof feature.properties?.label === 'string' ? feature.properties.label : '';
    const color = typeof feature.properties?.color === 'string' ? feature.properties.color : undefined;

    if (type === 'Point' && mode === 'text') {
      // The Text tool: the label is the whole shape, so there are no coordinates and no separate name.
      labels.push({ id, kind: 'text', position: feature.geometry.coordinates as Position, text: name || 'Text', color });
      continue;
    }
    if (name) {
      const anchor =
        type === 'Point'
          ? (feature.geometry.coordinates as Position)
          : type === 'LineString'
            ? pointAlong(feature.geometry.coordinates as Position[])
            : type === 'Polygon'
              ? ringCenter((feature.geometry.coordinates as Position[][])[0] ?? [])
              : null;
      if (anchor) labels.push({ id, kind: 'name', position: anchor, text: name });
    }

    if (type === 'Point') {
      const at = feature.geometry.coordinates as Position;
      labels.push({ id, kind: 'point', position: at, text: formatCoordinates(at) });
    } else if (type === 'LineString' && mode === 'highlighter') {
      // A highlighter stroke is for pointing at something, not measuring it: it shows only its name (added above).
      continue;
    } else if (type === 'LineString' && mode === 'angle') {
      const coords = feature.geometry.coordinates as Position[];
      if (coords.length >= 3) {
        labels.push({ id, kind: 'angle', position: coords[1], text: formatAngle(angleAt(coords[0], coords[1], coords[2])) });
      }
      segmentLabels(id, coords, options, true, labels);
    } else if (type === 'LineString') {
      const coords = feature.geometry.coordinates as Position[];
      if (coords.length < 2) continue;
      const total = lineLength(coords);
      const at = pointAlong(coords);
      if (at && total >= MIN_LABEL_LENGTH_M) {
        const single = coords.length === 2 && options.bearings;
        const text = single
          ? `${formatDistance(total, units)} · ${formatBearing(bearingBetween(coords[0], coords[1]))}`
          : formatDistance(total, units);
        labels.push({ id, kind: 'total', position: at, text });
      }
      if (coords.length > 2) segmentLabels(id, coords, options, false, labels);
      if (options.angles) {
        for (let i = 1; i < coords.length - 1; i++) {
          labels.push({ id, kind: 'angle', position: coords[i], text: formatAngle(angleAt(coords[i - 1], coords[i], coords[i + 1])) });
        }
      }
    } else if (type === 'Polygon') {
      const rings = feature.geometry.coordinates as Position[][];
      if (!rings[0] || rings[0].length < 4) continue;
      const ring = rings[0];
      const at = ringCenter(ring);
      const area = polygonArea(rings);
      if (!at || area < MIN_LABEL_AREA_M2) continue;
      const perimeter = lineLength(ring);
      if (mode === 'circle') {
        // The ring's corners are all one radius from the centre, so the radius is the centre to any corner.
        const radius = distanceBetween(at, ring[0]);
        labels.push({
          id,
          kind: 'total',
          position: at,
          text: `r ${formatDistance(radius, units)}\n${formatArea(area, units)}\n${formatDistance(perimeter, units)} around`,
        });
      } else {
        labels.push({ id, kind: 'total', position: at, text: `${formatArea(area, units)}\n${formatDistance(perimeter, units)} around` });
        const corners = openRing(ring);
        if (corners.length <= MAX_LABELLED_CORNERS) {
          segmentLabels(id, [...corners, corners[0]], options, false, labels);
          if (options.angles) {
            corners.forEach((corner, i) => {
              const before = corners[(i + corners.length - 1) % corners.length];
              const after = corners[(i + 1) % corners.length];
              labels.push({ id, kind: 'angle', position: corner, text: formatAngle(angleAt(before, corner, after)) });
            });
          }
        }
      }
    }
  }
  return labels;
}
