import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useDrawStore } from '../../state/drawStore';
import { useSettings } from '../../state/settings';
import { drawController } from './controller';
import type { DrawEngine } from './engine';
import { ensureDrawLayers, showDrawLayers } from './layers';
import type { LabelOptions, UnitSystem } from './measure';
import type { DrawPrefs } from './prefs';

// The measuring choices, with "auto" units resolved to whatever the Units setting says.
function labelOptions(prefs: DrawPrefs, appUnits: 'metric' | 'imperial'): LabelOptions {
  const units: UnitSystem = prefs.units === 'auto' ? appUnits : prefs.units;
  return { units, segments: prefs.segments, angles: prefs.angles, bearings: prefs.bearings };
}

// Attaches the drawing engine to the map the first time the tool is opened (it is a separate chunk, so people who never
// draw never download it), keeps the chosen tool and the text on the map in step, and detaches on unmount.
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
            useDrawStore.getState().bumpRevision();
            showDrawLayers(map, features, optionsRef.current);
          },
          onSelect: (id) => store.setSelectedId(id),
          onHistory: (state) => store.setHistory(state),
          onTool: (next) => store.setTool(next),
        });
        ensureDrawLayers(map);
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

  // Units or measuring choices changed: redraw the text.
  useEffect(() => {
    const map = mapRef.current;
    const engine = engineRef.current;
    if (map && engine) showDrawLayers(map, engine.features(), labelOptions(prefs, appUnits));
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
