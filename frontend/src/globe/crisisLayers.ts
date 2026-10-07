import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection, Point } from 'geojson';
import type { CrisisSummary } from '../api/types';
import { isDrawingOpen } from '../state/drawStore';
import { labelForSeverity, severityTone } from './severity';
import { pinTag, sourcesTag } from '../lib/precision';

// Crisis pins as a clustered GeoJSON source + circle layers, drawn by the GPU
// — replacing one DOM Marker (plus Popup) per event, which at tens of
// thousands of events froze pans and crashed mobile browsers. MapLibre's
// globe projection also occludes far-side layer features itself, so none of
// the old per-marker hemisphere math applies to these.
//
// One feature per *location*, not per event: the news feed places events at
// the centre of the place they name, so dozens share one exact coordinate
// (66 on London's centre, ~90 on the middle of the US). Events on the same
// coordinate are grouped into one pin that carries its event count, so a
// cluster's number is the number of pins under it, and a stacked pin can
// list all of its events instead of hiding all but one.

export const CRISIS_SOURCE_ID = 'crises';
const CLUSTER_LAYER_ID = 'crises-clusters';
const CLUSTER_COUNT_LAYER_ID = 'crises-cluster-count';
const HALO_LAYER_ID = 'crises-halo';
const POINT_LAYER_ID = 'crises-points';
const POINT_COUNT_LAYER_ID = 'crises-point-count';
const LAYER_IDS = [CLUSTER_LAYER_ID, CLUSTER_COUNT_LAYER_ID, HALO_LAYER_ID, POINT_LAYER_ID, POINT_COUNT_LAYER_ID];

// Position confidence assumed when an event doesn't say (the feed's city level).
const DEFAULT_CONFIDENCE = 85;

// Same thresholds as colorForSeverity() in severity.ts, as a style expression.
const severityStep = (property: string) =>
  ['step', ['get', property], '#22c55e', 20, '#84cc16', 40, '#eab308', 60, '#f97316', 80, '#dc2626'] as maplibregl.ExpressionSpecification;

// `id` is the location key; `n` is how many events share the location; `statement` is true
// when every event there is a statement; `prec` is the least precise confidence among them.
type CrisisCollection = FeatureCollection<
  Point,
  { id: string; n: number; severity: number; scope: string; statement: boolean; prec: number }
>;

// Events whose coordinates agree to 4 decimal places (about 11 m) share a pin.
export function locationKey(lat: number, lon: number): string {
  return `${lat.toFixed(4)},${lon.toFixed(4)}`;
}

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
    clusterProperties: { maxSeverity: ['max', ['get', 'severity']], events: ['+', ['get', 'n']] },
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

  // A faint ring under pins whose position is only approximate: the less precise
  // (country, then region, then city), the wider the ring. Exact places get none.
  map.addLayer({
    id: HALO_LAYER_ID,
    type: 'circle',
    source: CRISIS_SOURCE_ID,
    filter: ['all', ['!', ['has', 'point_count']], ['<', ['get', 'prec'], 90]],
    paint: {
      'circle-color': severityStep('severity'),
      'circle-opacity': 0.18,
      'circle-radius': ['step', ['get', 'prec'], 22, 56, 15, 71, 10],
    },
  });

  const isStatement = ['to-boolean', ['get', 'statement']] as maplibregl.ExpressionSpecification;
  map.addLayer({
    id: POINT_LAYER_ID,
    type: 'circle',
    source: CRISIS_SOURCE_ID,
    filter: ['!', ['has', 'point_count']],
    paint: {
      // Something that happened: filled with the severity colour. A statement: hollow,
      // with a thick severity-coloured edge.
      'circle-color': ['case', isStatement, 'rgba(10,14,20,0.35)', severityStep('severity')],
      // A pin holding several events is drawn larger so its count fits.
      'circle-radius': [
        'interpolate',
        ['linear'],
        ['zoom'],
        1,
        ['case', ['>', ['get', 'n'], 1], 8, 4],
        6,
        ['case', ['>', ['get', 'n'], 1], 11, 7],
      ],
      'circle-stroke-width': ['case', isStatement, 2.5, 1],
      'circle-stroke-color': ['case', isStatement, severityStep('severity'), 'rgba(255,255,255,0.8)'],
    },
  });

  map.addLayer({
    id: POINT_COUNT_LAYER_ID,
    type: 'symbol',
    source: CRISIS_SOURCE_ID,
    filter: ['all', ['!', ['has', 'point_count']], ['>', ['get', 'n'], 1]],
    layout: {
      'text-field': ['to-string', ['get', 'n']],
      'text-font': ['Noto Sans Bold'],
      'text-size': 10,
      'text-allow-overlap': true,
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': 'rgba(0,0,0,0.6)',
      'text-halo-width': 1,
    },
  });
}

export function removeCrisisLayers(map: maplibregl.Map): void {
  LAYER_IDS.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  if (map.getSource(CRISIS_SOURCE_ID)) map.removeSource(CRISIS_SOURCE_ID);
}

// Groups events by location (worst first within a location), sends one
// feature per location to the map worker, and returns the groups so a click
// can look up the events behind a pin. Only key/count/severity/scope go to
// the worker; everything else stays in the returned map.
export function setCrisisData(map: maplibregl.Map, crises: CrisisSummary[]): Map<string, CrisisSummary[]> {
  const groups = new Map<string, CrisisSummary[]>();
  for (const c of crises) {
    if (typeof c.lat !== 'number' || typeof c.lon !== 'number') continue;
    const key = locationKey(c.lat, c.lon);
    const group = groups.get(key);
    if (group) group.push(c);
    else groups.set(key, [c]);
  }

  const features: CrisisCollection['features'] = [];
  for (const [key, events] of groups) {
    events.sort((a, b) => b.severity - a.severity || b.date.localeCompare(a.date));
    const first = events[0];
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [first.lon as number, first.lat as number] },
      properties: {
        id: key,
        n: events.length,
        severity: first.severity,
        statement: events.every((e) => e.statement === true),
        prec: Math.min(...events.map((e) => e.location_confidence ?? DEFAULT_CONFIDENCE)),
        // Muted only when every event here is local reporting.
        scope: events.every((e) => e.scope === 'local') ? 'local' : 'global',
      },
    });
  }

  const source = map.getSource(CRISIS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
  source?.setData({ type: 'FeatureCollection', features });
  return groups;
}

// True when the point is over a crisis pin or cluster. Used to keep a pin
// click from also opening the country underneath it: layer click handlers
// fire independently, so the country hit-test layer must yield to pins.
export function hitsCrisisLayer(map: maplibregl.Map, point: maplibregl.PointLike): boolean {
  const layers = [CLUSTER_LAYER_ID, POINT_LAYER_ID].filter((id) => map.getLayer(id));
  return layers.length > 0 && map.queryRenderedFeatures(point, { layers }).length > 0;
}

interface InteractionHandlers {
  getGroup: (key: string) => CrisisSummary[] | undefined;
  onSelect: (crisis: CrisisSummary) => void;
}

// The list shown when a stacked pin is clicked: every event at that location,
// worst first. Built from DOM nodes (text only), never from HTML strings.
function stackedList(events: CrisisSummary[], onPick: (crisis: CrisisSummary) => void): HTMLElement {
  const root = document.createElement('div');
  root.className = 'geo-stack';
  const head = document.createElement('div');
  head.className = 'geo-stack-head';
  head.textContent = `${events.length} events at this location`;
  root.appendChild(head);
  const list = document.createElement('div');
  list.className = 'geo-stack-list';
  for (const crisis of events) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'geo-stack-row';
    const title = document.createElement('div');
    title.className = 'geo-pop-title';
    title.textContent = crisis.title;
    const meta = document.createElement('div');
    meta.className = 'geo-stack-meta';
    const dot = document.createElement('span');
    dot.className = `geo-dot geo-${severityTone(crisis.severity).replace('sev', 'sev-')}`;
    const text = document.createElement('span');
    text.textContent = `${crisis.country} · ${labelForSeverity(crisis.severity)} (${crisis.severity})`;
    meta.append(dot, text);
    const tag = [sourcesTag(crisis.sources), pinTag(crisis.location_confidence, crisis.statement)]
      .filter((t): t is string => !!t)
      .join(' · ');
    row.append(title, meta);
    if (tag) {
      const tagLine = document.createElement('div');
      tagLine.className = 'geo-pop-note';
      tagLine.textContent = tag;
      row.appendChild(tagLine);
    }
    row.addEventListener('click', () => onPick(crisis));
    list.appendChild(row);
  }
  root.appendChild(list);
  return root;
}

// Wires click/hover for the crisis layers; returns a detach function.
export function attachCrisisInteractions(map: maplibregl.Map, { getGroup, onSelect }: InteractionHandlers): () => void {
  const popup = new maplibregl.Popup({ offset: 10, className: 'geo-popup' });

  const onPointClick = (e: maplibregl.MapLayerMouseEvent) => {
    if (isDrawingOpen()) return;
    const key = e.features?.[0]?.properties?.id as string | undefined;
    const events = key ? getGroup(key) : undefined;
    if (!events || events.length === 0) return;
    const first = events[0];
    const at: [number, number] = [first.lon as number, first.lat as number];

    // Several events share this spot: list them all and let the user pick one.
    if (events.length > 1) {
      popup
        .setLngLat(at)
        .setDOMContent(
          stackedList(events, (crisis) => {
            onSelect(crisis);
            popup.remove();
          }),
        )
        .addTo(map);
      return;
    }

    onSelect(first);
    popup
      .setLngLat(at)
      .setHTML(
        `<div class="geo-pop-title">${escapeHtml(first.title)}</div><div class="geo-pop-meta">${escapeHtml(first.country)} &middot; ${labelForSeverity(first.severity)} (${first.severity})</div>` +
          [sourcesTag(first.sources), pinTag(first.location_confidence, first.statement)]
            .filter((tag): tag is string => !!tag)
            .map((tag) => `<div class="geo-pop-note">${escapeHtml(tag)}</div>`)
            .join(''),
      )
      .addTo(map);
  };

  const onClusterClick = async (e: maplibregl.MapLayerMouseEvent) => {
    if (isDrawingOpen()) return;
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
