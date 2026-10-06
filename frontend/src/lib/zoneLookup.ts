// Which time zone a map point is in, from the zone boundary file the map already draws
// (frontend/public/timezones.geojson, timezone-boundary-builder, OpenStreetMap-based data). The file merges
// zones that currently share the same offset rules, so the id returned is one representative zone whose
// current clock is right for every place inside the polygon.
// This file imports nothing so it can be unit-tested directly (frontend/tests/zoneLookup.test.ts).

type Ring = number[][];

interface Entry {
  tzid: string;
  bbox: [number, number, number, number];   // minLon, minLat, maxLon, maxLat
  rings: Ring[];                              // outer ring first, then holes
}

export interface ZoneIndex {
  entries: Entry[];
  cache: Map<string, string | null>;
}

interface GeoJsonLike {
  features?: {
    properties?: { tzid?: unknown } | null;
    geometry?: { type?: string; coordinates?: unknown } | null;
  }[];
}

function bboxOf(ring: Ring): [number, number, number, number] {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  for (const [lon, lat] of ring) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [minLon, minLat, maxLon, maxLat];
}

export function buildZoneIndex(geojson: GeoJsonLike): ZoneIndex {
  const entries: Entry[] = [];
  for (const feature of geojson.features ?? []) {
    const tzid = feature.properties?.tzid;
    const geometry = feature.geometry;
    if (typeof tzid !== 'string' || !geometry) continue;
    let polygons: Ring[][] = [];
    if (geometry.type === 'Polygon') polygons = [geometry.coordinates as Ring[]];
    else if (geometry.type === 'MultiPolygon') polygons = geometry.coordinates as Ring[][];
    for (const rings of polygons) {
      if (!Array.isArray(rings) || rings.length === 0 || !Array.isArray(rings[0])) continue;
      entries.push({ tzid, bbox: bboxOf(rings[0]), rings });
    }
  }
  return { entries, cache: new Map() };
}

function inRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// The zone id for a point, or null over open sea or where the file has no polygon.
export function zoneAt(index: ZoneIndex, lat: number, lon: number): string | null {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  const key = `${lat},${lon}`;
  const known = index.cache.get(key);
  if (known !== undefined) return known;
  let found: string | null = null;
  for (const entry of index.entries) {
    const [minLon, minLat, maxLon, maxLat] = entry.bbox;
    if (lon < minLon || lon > maxLon || lat < minLat || lat > maxLat) continue;
    if (!inRing(lon, lat, entry.rings[0])) continue;
    if (entry.rings.slice(1).some((hole) => inRing(lon, lat, hole))) continue;
    found = entry.tzid;
    break;
  }
  index.cache.set(key, found);
  return found;
}

let loading: Promise<ZoneIndex | null> | null = null;

// Fetches the boundary file once per page (the map has usually fetched it already, so it comes from cache).
export function loadZoneIndex(url = '/timezones.geojson'): Promise<ZoneIndex | null> {
  if (!loading) {
    loading = fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => (json ? buildZoneIndex(json) : null))
      .catch(() => null);
    // A failed load may be tried again later.
    loading.then((index) => {
      if (!index) loading = null;
    });
  }
  return loading;
}
