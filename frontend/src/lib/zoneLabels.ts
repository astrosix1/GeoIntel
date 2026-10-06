// Labels for the zone map: one point per zone (inside its biggest polygon), the zone's current offset and
// time, and a flag for offsets that people often get wrong. Pure logic so it can be tested
// (frontend/tests/zoneLabels.test.ts); the map layer that draws it is globe/zoneLabelLayer.ts.
import { pointInPolygonRings } from './zoneLookup.ts';
import { formatOffset, offsetMinutes } from './timezones.ts';

type Ring = number[][];

export interface LabelPoint {
  tzid: string;
  lon: number;
  lat: number;
  // Size of the polygon the point sits in (square degrees); larger zones win a crowded spot.
  area: number;
}

interface GeoJsonLike {
  features?: {
    properties?: { tzid?: unknown } | null;
    geometry?: { type?: string; coordinates?: unknown } | null;
  }[];
}

// Signed area of a ring in square degrees (shoelace).
function ringArea(ring: Ring): number {
  let sum = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) sum += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]);
  return sum / 2;
}

function centroid(ring: Ring): [number, number] {
  let area = 0, cx = 0, cy = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const cross = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
    area += cross;
    cx += (ring[j][0] + ring[i][0]) * cross;
    cy += (ring[j][1] + ring[i][1]) * cross;
  }
  if (area === 0) return [ring[0][0], ring[0][1]];
  return [cx / (3 * area), cy / (3 * area)];
}

// A point guaranteed to be inside the polygon: its centroid if that is inside, otherwise the inside point of
// a grid across its bounds that lies nearest the centroid (centroids of crescent-shaped zones fall outside).
export function interiorPoint(rings: Ring[]): [number, number] | null {
  const outer = rings[0];
  if (!outer || outer.length < 4) return null;
  const [cx, cy] = centroid(outer);
  if (pointInPolygonRings(cx, cy, rings)) return [cx, cy];
  const xs = outer.map((p) => p[0]);
  const ys = outer.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  let best: [number, number] | null = null;
  let bestDistance = Infinity;
  const STEPS = 24;
  for (let i = 0; i <= STEPS; i++) {
    for (let j = 0; j <= STEPS; j++) {
      const x = minX + ((maxX - minX) * i) / STEPS;
      const y = minY + ((maxY - minY) * j) / STEPS;
      if (!pointInPolygonRings(x, y, rings)) continue;
      const d = (x - cx) ** 2 + (y - cy) ** 2;
      if (d < bestDistance) {
        bestDistance = d;
        best = [x, y];
      }
    }
  }
  return best;
}

// One label point per zone id: in that zone's largest polygon.
export function labelPoints(geojson: GeoJsonLike): LabelPoint[] {
  const best = new Map<string, LabelPoint>();
  for (const feature of geojson.features ?? []) {
    const tzid = feature.properties?.tzid;
    const geometry = feature.geometry;
    if (typeof tzid !== 'string' || !geometry) continue;
    let polygons: Ring[][] = [];
    if (geometry.type === 'Polygon') polygons = [geometry.coordinates as Ring[]];
    else if (geometry.type === 'MultiPolygon') polygons = geometry.coordinates as Ring[][];
    for (const rings of polygons) {
      if (!Array.isArray(rings) || !Array.isArray(rings[0])) continue;
      const area = Math.abs(ringArea(rings[0]));
      const current = best.get(tzid);
      if (current && current.area >= area) continue;
      const point = interiorPoint(rings);
      if (point) best.set(tzid, { tzid, lon: point[0], lat: point[1], area });
    }
  }
  return [...best.values()];
}

// ---- unusual offsets --------------------------------------------------------------------------------------

// Offsets that are easy to misread: not a whole number of hours, or the far ends beside the date line.
export function isUnusualOffset(minutes: number | null): boolean {
  if (minutes === null) return false;
  return minutes % 60 !== 0 || minutes >= 13 * 60 || minutes <= -11 * 60;
}

// A one-line explanation for the zone panel, or null for an ordinary offset.
export function unusualOffsetNote(minutes: number | null): string | null {
  if (minutes === null) return null;
  const label = formatOffset(minutes);
  if (minutes % 60 !== 0) {
    const part = Math.abs(minutes) % 60 === 30 ? 'half-hour' : Math.abs(minutes) % 60 === 45 ? 'quarter-hour' : `${Math.abs(minutes) % 60}-minute`;
    return `${label} is a ${part} offset: clocks here are not a whole number of hours from UTC.`;
  }
  if (minutes >= 13 * 60) return `${label} is beside the International Date Line: this zone is among the first places on Earth to reach each new calendar day.`;
  if (minutes <= -11 * 60) return `${label} is beside the International Date Line: this zone is among the last places on Earth to reach each new calendar day.`;
  return null;
}

// ---- label text --------------------------------------------------------------------------------------------------

// "+9" or "+5:45" or "0": the offset without the "UTC", short enough for a map.
export function shortOffset(minutes: number | null): string {
  if (minutes === null) return '?';
  if (minutes === 0) return '0';
  const sign = minutes > 0 ? '+' : '-';
  const abs = Math.abs(minutes);
  const m = abs % 60;
  return `${sign}${Math.floor(abs / 60)}${m ? `:${String(m).padStart(2, '0')}` : ''}`;
}

export interface LabelFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: { text: string; unusual: boolean; area: number };
}

// The labels as map features, with the time at `at` in each zone ("23:30" and the offset below it).
export function labelFeatures(points: LabelPoint[], at: Date): { type: 'FeatureCollection'; features: LabelFeature[] } {
  const features: LabelFeature[] = [];
  for (const point of points) {
    const offset = offsetMinutes(point.tzid, at);
    if (offset === null) continue;
    const local = new Date(at.getTime() + offset * 60_000);
    const time = `${String(local.getUTCHours()).padStart(2, '0')}:${String(local.getUTCMinutes()).padStart(2, '0')}`;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [point.lon, point.lat] },
      properties: { text: `${time}\n${shortOffset(offset)}`, unusual: isUnusualOffset(offset), area: point.area },
    });
  }
  return { type: 'FeatureCollection', features };
}
