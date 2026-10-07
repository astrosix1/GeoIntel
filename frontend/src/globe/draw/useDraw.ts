import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useDrawStore } from '../../state/drawStore';
import { useSettings } from '../../state/settings';
import { drawController } from './controller';
import type { DrawEngine, DrawFeature } from './engine';
import { labelsFor } from './measure';
import type { UnitSystem } from './measure';

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
        'text-size': 12,
        'text-line-height': 1.2,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        'text-padding': 2,
      },
      paint: { 'text-color': '#0f172a', 'text-halo-color': '#ffffff', 'text-halo-width': 2 },
    });
  } else {
    // Keep the labels above anything added since (the drawing's own layers are added when the engine starts).
    map.moveLayer(LABEL_LAYER);
  }
}

function showLabels(map: maplibregl.Map, features: DrawFeature[], units: UnitSystem): void {
  const source = map.getSource(LABEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  const labels = labelsFor(features, units);
  source.setData({
    type: 'FeatureCollection',
    features: labels.map((label) => ({
      type: 'Feature',
      properties: { text: label.text, id: label.id },
      geometry: { type: 'Point', coordinates: label.position },
    })),
  });
}

// Attaches the drawing engine to the map the first time the tool is opened (it is a separate chunk, so people who never
// draw never download it), keeps the chosen tool and the measurement labels in step, and detaches on unmount.
export function useDraw(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean): void {
  const open = useDrawStore((s) => s.open);
  const tool = useDrawStore((s) => s.tool);
  const units = useSettings((s) => s.units);
  const engineRef = useRef<DrawEngine | null>(null);
  const loadingRef = useRef(false);
  const unitsRef = useRef(units);
  unitsRef.current = units;

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
            showLabels(map, features, unitsRef.current);
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

  // Units changed in Settings: redraw the labels.
  useEffect(() => {
    const map = mapRef.current;
    const engine = engineRef.current;
    if (map && engine) showLabels(map, engine.features(), units);
  }, [units, mapRef]);

  useEffect(
    () => () => {
      drawController.attach(null);
      engineRef.current?.destroy();
      engineRef.current = null;
    },
    [],
  );
}
