import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useDrawStore } from '../../state/drawStore';
import { useSettings } from '../../state/settings';
import { drawController } from './controller';
import type { DrawEngine, DrawFeature } from './engine';
import { labelsFor } from './measure';
import type { LabelOptions, UnitSystem } from './measure';
import type { DrawPrefs } from './prefs';

const LABEL_SOURCE = 'draw-measure';
const LABEL_LAYER = 'draw-measure-labels';

// Measurements are drawn as text on the map, from the shapes' own geometry, in the user's units.
function ensureLabelLayer(map: maplibregl.Map): void {
  if (!map.getSource(LABEL_SOURCE)) {
    map.addSource(LABEL_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer(LABEL_LAYER)) {
    map.addLayer({
      id: LABEL_LAYER,
      type: 'symbol',
      source: LABEL_SOURCE,
      layout: {
        'text-field': ['get', 'text'],
        'text-font': ['Noto Sans Bold'],
        // Totals are the main figure; the per-segment and per-corner figures are smaller. Angles sit off their corner.
        'text-size': ['match', ['get', 'kind'], 'total', 13, 'point', 11, 11],
        'text-offset': ['match', ['get', 'kind'], 'angle', ['literal', [1.6, -1.1]], ['literal', [0, 0]]],
        'text-line-height': 1.2,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        'text-padding': 2,
      },
      paint: {
        'text-color': ['match', ['get', 'kind'], 'angle', '#9a3412', 'segment', '#1e3a8a', '#0f172a'],
        'text-halo-color': '#ffffff',
        'text-halo-width': 2,
      },
    });
  } else {
    // Keep the labels above anything added since (the drawing's own layers are added when the engine starts).
    map.moveLayer(LABEL_LAYER);
  }
}

function showLabels(map: maplibregl.Map, features: DrawFeature[], options: LabelOptions): void {
  const source = map.getSource(LABEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const labels = labelsFor(features, options);
  source.setData({
    type: 'FeatureCollection',
    features: labels.map((label) => ({
      type: 'Feature',
      properties: { text: label.text, id: label.id, kind: label.kind },
      geometry: { type: 'Point', coordinates: label.position },
    })),
  });
}

// Attaches the drawing engine to the map the first time the tool is opened (it is a separate chunk, so people who never
// draw never download it), keeps the chosen tool and the measurement labels in step, and detaches on unmount.
// The measuring choices, with "auto" units resolved to whatever the Units setting says.
function labelOptions(prefs: DrawPrefs, appUnits: 'metric' | 'imperial'): LabelOptions {
  const units: UnitSystem = prefs.units === 'auto' ? appUnits : prefs.units;
  return { units, segments: prefs.segments, angles: prefs.angles, bearings: prefs.bearings };
}

export function useDraw(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean): void {
  const open = useDrawStore((s) => s.open);
  const tool = useDrawStore((s) => s.tool);
  const appUnits = useSettings((s) => s.units);
  const prefs = useDrawStore((s) => s.prefs);
  const engineRef = useRef<DrawEngine | null>(null);
  const loadingRef = useRef(false);
  const optionsRef = useRef(labelOptions(prefs, appUnits));
  optionsRef.current = labelOptions(prefs, appUnits);

  // Start the engine on first open.
  useEffect(() => {
    const map = mapRef.current;
    if (!open || !mapReady || !map || engineRef.current || loadingRef.current) return;
    loadingRef.current = true;
    import('./engine')
      .then(({ createDrawEngine }) => {
        if (mapRef.current !== map) return;
        const store = useDrawStore.getState();
        const engine = createDrawEngine(map, {
          onChange: (features) => {
            useDrawStore.getState().setShapeCount(features.length);
            showLabels(map, features, optionsRef.current);
          },
          onSelect: (id) => store.setSelectedId(id),
          onHistory: (state) => store.setHistory(state),
        });
        ensureLabelLayer(map);
        engineRef.current = engine;
        drawController.attach(engine);
        const current = useDrawStore.getState();
        engine.setTool(current.open ? current.tool : null);
      })
      .finally(() => {
        loadingRef.current = false;
      });
  }, [open, mapReady, mapRef]);

  // The chosen tool, or hidden when the toolbar is closed (the drawing stays on the map).
  useEffect(() => {
    engineRef.current?.setTool(open ? tool : null);
    if (!open) useDrawStore.getState().setSelectedId(null);
  }, [open, tool]);

  // Units or measuring choices changed: redraw the labels.
  useEffect(() => {
    const map = mapRef.current;
    const engine = engineRef.current;
    if (map && engine) showLabels(map, engine.features(), labelOptions(prefs, appUnits));
  }, [prefs, appUnits, mapRef]);

  useEffect(
    () => () => {
      drawController.attach(null);
      engineRef.current?.destroy();
      engineRef.current = null;
    },
    [],
  );
}
