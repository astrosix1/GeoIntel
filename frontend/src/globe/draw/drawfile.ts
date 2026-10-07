import { cleanLayers, MAX_LAYERS } from './drawlayers.ts';
import type { DrawLayer } from './drawlayers.ts';
import { cleanStyle } from './style.ts';
import type { ShapeStyle } from './style.ts';

// What a drawing is made of when it is saved, kept as a draft, exported or imported: its layers and its shapes as plain
// GeoJSON, with each shape's mode, style and layer in its properties. Reading is strict: only the shapes and fields the tool
// knows are kept, whatever the file said. The backend applies the same rules (backend/services/drawings.py), so a file that
// passes here is one the server will take. This file imports only pure modules so it can be unit-tested
// (frontend/tests/drawfile.test.ts).

export const DRAWING_VERSION = 1;
export const MAX_SHAPES = 500;
export const MAX_VERTICES = 20_000;
export const MAX_BYTES = 1_000_000;

const MODES = ['point', 'text', 'linestring', 'arrow', 'angle', 'polygon', 'rectangle', 'circle', 'freehand', 'highlighter'];
const FOREIGN_MODE: Record<string, string> = { Point: 'point', LineString: 'linestring', Polygon: 'polygon' };

export type Position = [number, number];

export interface DrawingGeometry {
  type: 'Point' | 'LineString' | 'Polygon';
  coordinates: Position | Position[] | Position[][];
}

export interface DrawingFeature {
  id?: string;
  type: 'Feature';
  geometry: DrawingGeometry;
  properties: ShapeStyle & { mode: string; layer: string };
}

export interface DrawingData {
  version: number;
  layers: DrawLayer[];
  features: DrawingFeature[];
}

export interface EngineFeature {
  id?: string | number;
  geometry: { type: string; coordinates: unknown };
  properties?: Record<string, unknown> | null;
}

const ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

// The drawing to save, from the shapes the engine holds and the layers the store holds.
export function buildDrawing(features: EngineFeature[], layers: DrawLayer[]): DrawingData {
  const clean = cleanLayers(layers);
  const known = new Set(clean.map((l) => l.id));
  const shapes: DrawingFeature[] = [];
  for (const feature of features) {
    const mode = feature.properties?.mode;
    const geometry = readGeometry(feature.geometry);
    if (typeof mode !== 'string' || !MODES.includes(mode) || !geometry) continue;
    const layer = feature.properties?.layer;
    const shape: DrawingFeature = {
      type: 'Feature',
      geometry: geometry.geometry,
      properties: { ...cleanStyle(feature.properties ?? {}), mode, layer: typeof layer === 'string' && known.has(layer) ? layer : clean[0].id },
    };
    if (typeof feature.id === 'string' && ID_PATTERN.test(feature.id)) shape.id = feature.id;
    shapes.push(shape);
  }
  return { version: DRAWING_VERSION, layers: clean, features: shapes };
}

function readPosition(value: unknown): Position | null {
  if (!Array.isArray(value) || (value.length !== 2 && value.length !== 3)) return null;
  const [lon, lat] = value;
  if (typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (value.length === 3 && (typeof value[2] !== 'number' || !Number.isFinite(value[2]))) return null;
  // A drawing across the date line on a flat map can run past 180; anything wilder is not a place.
  if (lon < -540 || lon > 540 || lat < -90 || lat > 90) return null;
  // The drawing engine refuses more than nine decimal places (about a tenth of a millimetre), and files from other tools
  // often carry far more, so every position is rounded to that.
  // GeoJSON longitudes run from -180 to 180, which is all the engine accepts: one written past that (a shape drawn across the
  // date line on a flat map, continuing on 181, 182...) is wrapped round to the same place.
  const wrapped = lon > 180 || lon < -180 ? ((((lon + 180) % 360) + 360) % 360) - 180 : lon;
  return [Math.round(wrapped * 1e9) / 1e9, Math.round(lat * 1e9) / 1e9];
}

function readGeometry(geometry: { type: string; coordinates: unknown } | null | undefined): { geometry: DrawingGeometry; vertices: number } | null {
  if (!geometry) return null;
  const coords = geometry.coordinates;
  if (geometry.type === 'Point') {
    const p = readPosition(coords);
    return p ? { geometry: { type: 'Point', coordinates: p }, vertices: 1 } : null;
  }
  if (geometry.type === 'LineString') {
    if (!Array.isArray(coords) || coords.length < 2) return null;
    const line = coords.map(readPosition);
    return line.every((p): p is Position => p !== null) ? { geometry: { type: 'LineString', coordinates: line }, vertices: line.length } : null;
  }
  if (geometry.type === 'Polygon') {
    if (!Array.isArray(coords) || coords.length === 0 || coords.length > 10) return null;
    const rings: Position[][] = [];
    let vertices = 0;
    for (const ring of coords) {
      if (!Array.isArray(ring) || ring.length < 4) return null;
      const cleaned = ring.map(readPosition);
      if (!cleaned.every((p): p is Position => p !== null)) return null;
      rings.push(cleaned as Position[]);
      vertices += cleaned.length;
    }
    return { geometry: { type: 'Polygon', coordinates: rings }, vertices };
  }
  return null;
}

export interface ParsedDrawing {
  data: DrawingData;
  // Shapes in the file that the tool cannot draw (for example multi-part shapes), left out.
  skipped: number;
}

export type ParseError = 'format' | 'empty' | 'too_many_shapes' | 'too_many_vertices' | 'too_large';

// Reads a drawing from stored data or an imported file: either this tool's own format, or any GeoJSON FeatureCollection
// (a single Feature is accepted too). Shapes the tool cannot draw are skipped and counted, not fatal.
export function parseDrawing(value: unknown): { ok: true; drawing: ParsedDrawing } | { ok: false; error: ParseError } {
  if (typeof value !== 'object' || value === null) return { ok: false, error: 'format' };
  const root = value as Record<string, unknown>;
  let rawFeatures: unknown[];
  let rawLayers: unknown = (root.geointel as Record<string, unknown> | undefined)?.layers ?? root.layers;
  if (root.type === 'FeatureCollection' && Array.isArray(root.features)) rawFeatures = root.features;
  else if (root.type === 'Feature') rawFeatures = [root];
  else if (Array.isArray(root.features)) rawFeatures = root.features;
  else return { ok: false, error: 'format' };
  if (rawFeatures.length > MAX_SHAPES * 4) return { ok: false, error: 'too_many_shapes' };

  const layers = cleanLayers(rawLayers).slice(0, MAX_LAYERS);
  const known = new Set(layers.map((l) => l.id));
  const features: DrawingFeature[] = [];
  let skipped = 0;
  let vertices = 0;
  for (const item of rawFeatures) {
    const feature = item as { id?: unknown; geometry?: { type: string; coordinates: unknown }; properties?: Record<string, unknown> | null };
    const geometry = typeof feature === 'object' && feature !== null ? readGeometry(feature.geometry) : null;
    if (!geometry) {
      skipped += 1;
      continue;
    }
    const props = feature.properties ?? {};
    const declared = props.mode;
    const mode = typeof declared === 'string' && MODES.includes(declared) ? declared : FOREIGN_MODE[geometry.geometry.type];
    // A name from another tool's file ("name" or "title") becomes the shape's name.
    const style = cleanStyle({ ...props, label: props.label ?? props.name ?? props.title });
    const layer = typeof props.layer === 'string' && known.has(props.layer) ? props.layer : layers[0].id;
    vertices += geometry.vertices;
    if (vertices > MAX_VERTICES) return { ok: false, error: 'too_many_vertices' };
    if (features.length >= MAX_SHAPES) return { ok: false, error: 'too_many_shapes' };
    const shape: DrawingFeature = { type: 'Feature', geometry: geometry.geometry, properties: { ...style, mode, layer } };
    if (typeof feature.id === 'string' && ID_PATTERN.test(feature.id)) shape.id = feature.id;
    features.push(shape);
  }
  if (features.length === 0 && skipped === 0) return { ok: false, error: 'empty' };
  return { ok: true, drawing: { data: { version: DRAWING_VERSION, layers, features }, skipped } };
}

// The drawing as a GeoJSON FeatureCollection other tools can open. The layers ride along in a `geointel` member, which other
// tools ignore and this one reads back; each shape's layer, style and name are in its properties.
export function toGeoJSON(data: DrawingData, name: string): string {
  return JSON.stringify(
    { type: 'FeatureCollection', name, geointel: { version: data.version, layers: data.layers }, features: data.features },
    null,
    2,
  );
}

// A safe file name for an export: letters, digits and dashes, never empty.
export function exportFileName(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  return `${slug || 'drawing'}.geojson`;
}

export function drawingSize(data: DrawingData): number {
  return JSON.stringify(data).length;
}
