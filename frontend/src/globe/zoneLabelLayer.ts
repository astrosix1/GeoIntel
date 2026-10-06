import * as maplibregl from 'maplibre-gl';
import { labelFeatures } from '../lib/zoneLabels';
import type { LabelPoint } from '../lib/zoneLabels';

// A time and offset label on every zone, drawn on the map itself. Bigger zones are placed first and a label
// that would overlap another is left out, so labels thin out on their own as the view changes. The font is one
// the base map style already serves.
const SOURCE_ID = 'timezone-labels-src';
const LAYER_ID = 'timezone-labels';

export function clearZoneLabels(map: maplibregl.Map) {
  if (!map.getStyle()) return;
  if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
}

export function setZoneLabels(map: maplibregl.Map, points: LabelPoint[], at: Date) {
  if (!map.getStyle()) return;
  const data = labelFeatures(points, at) as unknown as GeoJSON.FeatureCollection;
  const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(SOURCE_ID, { type: 'geojson', data });
  map.addLayer({
    id: LAYER_ID,
    type: 'symbol',
    source: SOURCE_ID,
    layout: {
      'text-field': ['get', 'text'],
      'text-font': ['Noto Sans Bold'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 0, 9, 4, 13],
      'text-line-height': 1.1,
      'text-allow-overlap': false,
      'text-padding': 10,
      'symbol-sort-key': ['-', 0, ['get', 'area']],
    },
    paint: {
      // Offsets that are easy to misread (half-hour, quarter-hour, date-line) are drawn in amber.
      'text-color': ['case', ['get', 'unusual'], '#fcd34d', '#f1f5f9'],
      'text-halo-color': '#0a0e14',
      'text-halo-width': 1.6,
    },
  });
}
