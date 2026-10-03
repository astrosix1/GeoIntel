import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection, Point } from 'geojson';
import type { CrisisSummary } from '../api/types';

// Crisis pins as a clustered GeoJSON source + circle layers, drawn by the GPU
// — replacing one DOM Marker (plus Popup) per event, which at tens of
// thousands of events froze pans and crashed mobile browsers. MapLibre's
// globe projection also occludes far-side layer features itself, so none of
// the old per-marker hemisphere math applies to these. One feature per event.

export const CRISIS_SOURCE_ID = 'crises';
const CLUSTER_LAYER_ID = 'crises-clusters';
const CLUSTER_COUNT_LAYER_ID = 'crises-cluster-count';
const POINT_LAYER_ID = 'crises-points';
const LAYER_IDS = [CLUSTER_LAYER_ID, CLUSTER_COUNT_LAYER_ID, POINT_LAYER_ID];

// Same thresholds as colorForSeverity() in severity.ts, as a style expression.
const severityStep = (property: string) =>
  ['step', ['get', property], '#22c55e', 20, '#eab308', 50, '#f97316', 80, '#dc2626'] as maplibregl.ExpressionSpecification;

type CrisisCollection = FeatureCollection<Point, { id: string; severity: number; scope: string }>;

const EMPTY: CrisisCollection = { type: 'FeatureCollection', features: [] };

export function escapeHtml(value: string): string {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

export function addCrisisLayers(map: maplibregl.Map): void {
  if (map.getSource(CRISIS_SOURCE_ID)) return;

  map.addSource(CRISIS_SOURCE_ID, {
    type: 'geojson',
    data: EMPTY,
    cluster: true,
    clusterRadius: 45,
    clusterMaxZoom: 6,
    // A cluster takes the colour of the worst event inside it.
    clusterProperties: { maxSeverity: ['max', ['get', 'severity']] },
  });

  map.addLayer({
    id: CLUSTER_LAYER_ID,
    type: 'circle',
    source: CRISIS_SOURCE_ID,
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': severityStep('maxSeverity'),
      'circle-radius': ['step', ['get', 'point_count'], 14, 100, 18, 1000, 24],
      'circle-opacity': 0.9,
      'circle-stroke-width': 1.5,
      'circle-stroke-color': 'rgba(255,255,255,0.85)',
    },
  });

  map.addLayer({
    id: CLUSTER_COUNT_LAYER_ID,
    type: 'symbol',
    source: CRISIS_SOURCE_ID,
    filter: ['has', 'point_count'],
    layout: {
      'text-field': ['get', 'point_count_abbreviated'],
      // A font the OpenFreeMap style's glyph server actually serves.
      'text-font': ['Noto Sans Bold'],
      'text-size': 11,
      'text-allow-overlap': true,
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': 'rgba(0,0,0,0.55)',
      'text-halo-width': 1,
    },
  });

  map.addLayer({
    id: POINT_LAYER_ID,
    type: 'circle',
    source: CRISIS_SOURCE_ID,
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': severityStep('severity'),
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4, 6, 7],
      'circle-stroke-width': 1,
      'circle-stroke-color': 'rgba(255,255,255,0.8)',
    },
  });
}

export function removeCrisisLayers(map: maplibregl.Map): void {
  LAYER_IDS.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  if (map.getSource(CRISIS_SOURCE_ID)) map.removeSource(CRISIS_SOURCE_ID);
}

// Only id/severity/scope go to the map worker; everything else is looked up
// from the summary by id when a pin is clicked.
export function setCrisisData(map: maplibregl.Map, crises: CrisisSummary[]): void {
  const source = map.getSource(CRISIS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const features: CrisisCollection['features'] = [];
  for (const c of crises) {
    if (typeof c.lat !== 'number' || typeof c.lon !== 'number') continue;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
      properties: { id: c.id, severity: c.severity, scope: c.scope ?? 'global' },
    });
  }
  source.setData({ type: 'FeatureCollection', features });
}

// True when the point is over a crisis pin or cluster. Used to keep a pin
// click from also opening the country underneath it: layer click handlers
// fire independently, so the country hit-test layer must yield to pins.
export function hitsCrisisLayer(map: maplibregl.Map, point: maplibregl.PointLike): boolean {
  const layers = [CLUSTER_LAYER_ID, POINT_LAYER_ID].filter((id) => map.getLayer(id));
  return layers.length > 0 && map.queryRenderedFeatures(point, { layers }).length > 0;
}

interface InteractionHandlers {
  getById: (id: string) => CrisisSummary | undefined;
  onSelect: (crisis: CrisisSummary) => void;
}

// Wires click/hover for the crisis layers; returns a detach function.
export function attachCrisisInteractions(map: maplibregl.Map, { getById, onSelect }: InteractionHandlers): () => void {
  const popup = new maplibregl.Popup({ offset: 10 });

  const onPointClick = (e: maplibregl.MapLayerMouseEvent) => {
    const id = e.features?.[0]?.properties?.id as string | undefined;
    const crisis = id ? getById(id) : undefined;
    if (!crisis) return;
    onSelect(crisis);
    popup
      .setLngLat([crisis.lon, crisis.lat])
      .setHTML(
        `<strong>${escapeHtml(crisis.title)}</strong><br/>${escapeHtml(crisis.country)} &middot; severity ${crisis.severity}`,
      )
      .addTo(map);
  };

  const onClusterClick = async (e: maplibregl.MapLayerMouseEvent) => {
    const feature = e.features?.[0];
    const clusterId = feature?.properties?.cluster_id as number | undefined;
    const source = map.getSource(CRISIS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (clusterId === undefined || !source || feature?.geometry.type !== 'Point') return;
    const zoom = await source.getClusterExpansionZoom(clusterId);
    map.easeTo({ center: feature.geometry.coordinates as [number, number], zoom });
  };

  const setPointer = () => {
    map.getCanvas().style.cursor = 'pointer';
  };
  const clearPointer = () => {
    map.getCanvas().style.cursor = '';
  };

  map.on('click', POINT_LAYER_ID, onPointClick);
  map.on('click', CLUSTER_LAYER_ID, onClusterClick);
  [POINT_LAYER_ID, CLUSTER_LAYER_ID].forEach((id) => {
    map.on('mouseenter', id, setPointer);
    map.on('mouseleave', id, clearPointer);
  });

  return () => {
    map.off('click', POINT_LAYER_ID, onPointClick);
    map.off('click', CLUSTER_LAYER_ID, onClusterClick);
    [POINT_LAYER_ID, CLUSTER_LAYER_ID].forEach((id) => {
      map.off('mouseenter', id, setPointer);
      map.off('mouseleave', id, clearPointer);
    });
    popup.remove();
  };
}
