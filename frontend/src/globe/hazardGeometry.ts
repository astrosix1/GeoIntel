import * as maplibregl from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { HazardDetail } from '../api/types';

// What GDACS publishes around the selected hazard, drawn under the pins:
// a cyclone's past path (solid) and forecast path (dashed), its wind zones and
// uncertainty cone, or a flood / wildfire's affected area. A part GDACS does not
// publish is simply absent.
const SOURCE_ID = 'hazard-geo-src';
const LAYERS = ['hazard-geo-area', 'hazard-geo-cone', 'hazard-geo-zone', 'hazard-geo-zone-line', 'hazard-geo-past', 'hazard-geo-forecast'];

const ZONE_COLORS = { Green: '#34c759', Orange: '#ff9500', Red: '#ff2d55' } as const;

type Props = { kind: string; level?: string; category?: string | null; label?: string };

export function hazardCollection(detail: HazardDetail | null | undefined): FeatureCollection<Geometry, Props> {
  const features: Feature<Geometry, Props>[] = [];
  const add = (list: HazardDetail['track'], kind: (f: Feature<Geometry, Record<string, unknown>>) => string) => {
    for (const f of list ?? []) {
      features.push({
        type: 'Feature',
        geometry: f.geometry,
        properties: {
          kind: kind(f),
          level: typeof f.properties?.level === 'string' ? f.properties.level : undefined,
          category: typeof f.properties?.category === 'string' ? f.properties.category : null,
          label: typeof f.properties?.label === 'string' ? f.properties.label : undefined,
        },
      });
    }
  };
  if (detail) {
    add(detail.area, () => 'area');
    add(detail.cone, () => 'cone');
    add(detail.wind_zones, () => 'zone');
    add(detail.track, (f) => (f.properties?.forecast ? 'forecast' : 'past'));
  }
  return { type: 'FeatureCollection', features };
}

export function clearHazardGeometry(map: maplibregl.Map) {
  if (!map.getStyle()) return;
  for (const id of LAYERS) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
}

export function setHazardGeometry(map: maplibregl.Map, detail: HazardDetail | null | undefined) {
  clearHazardGeometry(map);
  const data = hazardCollection(detail);
  if (!map.getStyle() || data.features.length === 0) return;
  map.addSource(SOURCE_ID, { type: 'geojson', data });
  const levelColor = ['match', ['get', 'level'], 'Red', ZONE_COLORS.Red, 'Orange', ZONE_COLORS.Orange, ZONE_COLORS.Green] as maplibregl.ExpressionSpecification;
  map.addLayer({
    id: 'hazard-geo-area', type: 'fill', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'area'],
    paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.25, 'fill-outline-color': '#38bdf8' },
  });
  map.addLayer({
    id: 'hazard-geo-cone', type: 'fill', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'cone'],
    paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.12, 'fill-outline-color': '#ffffff' },
  });
  map.addLayer({
    id: 'hazard-geo-zone', type: 'fill', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'zone'],
    paint: { 'fill-color': levelColor, 'fill-opacity': 0.14 },
  });
  map.addLayer({
    id: 'hazard-geo-zone-line', type: 'line', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'zone'],
    paint: { 'line-color': levelColor, 'line-width': 1.5, 'line-opacity': 0.9 },
  });
  map.addLayer({
    id: 'hazard-geo-past', type: 'line', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'past'],
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': '#f8fafc', 'line-width': 3 },
  });
  map.addLayer({
    id: 'hazard-geo-forecast', type: 'line', source: SOURCE_ID, filter: ['==', ['get', 'kind'], 'forecast'],
    paint: { 'line-color': '#f8fafc', 'line-width': 3, 'line-dasharray': [1.5, 1.5] },
  });
}
