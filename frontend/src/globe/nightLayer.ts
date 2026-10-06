import * as maplibregl from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { nightRing, terminatorLine } from '../lib/sun';

// The night side of the Earth, shaded, with the sunrise/sunset line, worked out from the date alone
// (lib/sun.ts). Redrawn by its caller once a minute and whenever the time slider moves.
const SOURCE_ID = 'night-src';
const FILL_ID = 'night-fill';
const LINE_ID = 'night-line';

function collection(date: Date): FeatureCollection<Geometry, { kind: string }> {
  const night: Feature<Geometry, { kind: string }> = {
    type: 'Feature',
    properties: { kind: 'night' },
    geometry: { type: 'Polygon', coordinates: [nightRing(date)] },
  };
  const line: Feature<Geometry, { kind: string }> = {
    type: 'Feature',
    properties: { kind: 'terminator' },
    geometry: { type: 'LineString', coordinates: terminatorLine(date) },
  };
  return { type: 'FeatureCollection', features: [night, line] };
}

export function clearNight(map: maplibregl.Map) {
  if (!map.getStyle()) return;
  if (map.getLayer(LINE_ID)) map.removeLayer(LINE_ID);
  if (map.getLayer(FILL_ID)) map.removeLayer(FILL_ID);
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
}

export function setNight(map: maplibregl.Map, date: Date) {
  if (!map.getStyle()) return;
  const data = collection(date);
  const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(SOURCE_ID, { type: 'geojson', data });
  map.addLayer({
    id: FILL_ID,
    type: 'fill',
    source: SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'night'],
    paint: { 'fill-color': '#050b1f', 'fill-opacity': 0.45 },
  });
  map.addLayer({
    id: LINE_ID,
    type: 'line',
    source: SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'terminator'],
    paint: { 'line-color': '#fcd34d', 'line-width': 1.2, 'line-opacity': 0.7 },
  });
}
