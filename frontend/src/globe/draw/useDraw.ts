import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useDrawStore } from '../../state/drawStore';
import { useSettings } from '../../state/settings';
import { drawController } from './controller';
import type { DrawEngine, DrawFeature } from './engine';
import { ensureDrawLayers, setLabelScale, showDrawLayers } from './layers';
import { labelsFor } from './measure';
import { MODE_NAMES } from './modenames';
import type { LabelOptions, UnitSystem } from './measure';
import { hiddenIds } from './drawlayers';
import type { DrawPrefs } from './prefs';
import { loadDraft, saveDraft } from './draft';
import { currentDrawing } from './session';
import { isLoadedLayers, isLoadingDrawing, openDrawing } from './session';

// The measuring choices, with "auto" units resolved to whatever the Units setting says.
function labelOptions(prefs: DrawPrefs, appUnits: 'metric' | 'imperial'): LabelOptions {
  const units: UnitSystem = prefs.units === 'auto' ? appUnits : prefs.units;
  return { units, segments: prefs.segments, angles: prefs.angles, bearings: prefs.bearings };
}

// Attaches the drawing engine to the map the first time the tool is opened (it is a separate chunk, so people who never
// draw never download it), keeps the chosen tool and the text on the map in step, and detaches on unmount.
export function useDraw(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean): void {
  const open = useDrawStore((s) => s.open);
  const presenting = useDrawStore((s) => s.presenting);
  const tool = useDrawStore((s) => s.tool);
  const appUnits = useSettings((s) => s.units);
  const prefs = useDrawStore((s) => s.prefs);
  const engineRef = useRef<DrawEngine | null>(null);
  const loadingRef = useRef(false);
  const draftTimer = useRef<number | undefined>(undefined);
  // The map's text is redrawn at most once per frame, however many changes arrive (a drag sends one per mouse move).
  const pendingFeatures = useRef<DrawFeature[] | null>(null);
  const frame = useRef(0);
  const optionsRef = useRef(labelOptions(prefs, appUnits));
  optionsRef.current = labelOptions(prefs, appUnits);

  // Keeps the draft up to date a moment after the last change (not on every mouse move).
  function scheduleDraft() {
    window.clearTimeout(draftTimer.current);
    draftTimer.current = window.setTimeout(() => {
      const { drawing, dirty } = useDrawStore.getState();
      saveDraft({ drawing, data: currentDrawing(), dirty });
    }, 600);
  }

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
            const state = useDrawStore.getState();
            pendingFeatures.current = features;
            if (!frame.current) {
              frame.current = window.requestAnimationFrame(() => {
                frame.current = 0;
                const latest = pendingFeatures.current;
                if (!latest) return;
                const current = useDrawStore.getState();
                current.setShapeCount(latest.length);
                current.bumpRevision();
                showDrawLayers(map, latest, optionsRef.current);
              });
            }
            if (!isLoadingDrawing()) {
              state.setDirty(true);
              scheduleDraft();
            }
          },
          onSelect: (id) => store.setSelectedId(id),
          onHistory: (state) => store.setHistory(state),
          onTool: (next) => store.setTool(next),
          // Tells screen readers what was just drawn, with its main measurement.
          onDrawn: (feature) => {
            const mode = String(feature.properties?.mode ?? '');
            const first = labelsFor([feature], optionsRef.current).find((l) => l.kind !== 'name' && l.kind !== 'text');
            const text = first ? `: ${first.text.split(String.fromCharCode(10)).join(', ')}` : '';
            useDrawStore.getState().setAnnouncement(`${MODE_NAMES[mode] ?? 'Shape'} added${text}`);
          },
          // A new shape goes on the active layer; if that layer is hidden it is shown first, so the shape does not vanish.
          getActiveLayer: () => {
            const { activeLayerId, layers, setActiveLayer } = useDrawStore.getState();
            if (layers.some((l) => l.id === activeLayerId && !l.visible)) setActiveLayer(activeLayerId);
            return useDrawStore.getState().activeLayerId;
          },
        });
        ensureDrawLayers(map);
        engineRef.current = engine;
        drawController.attach(engine);
        engine.setHiddenLayers(hiddenIds(useDrawStore.getState().layers));
        // Pick up where the last visit left off: the draft kept in this browser.
        const draft = loadDraft();
        if (draft) {
          openDrawing({ version: 1, layers: draft.data.layers, features: draft.data.features }, draft.drawing, draft.dirty !== false);
        }
        const current = useDrawStore.getState();
        engine.setTool(current.open && !current.presenting ? current.tool : null);
      })
      .finally(() => {
        loadingRef.current = false;
      });
  }, [open, mapReady, mapRef]);

  // The chosen tool, or hidden when the toolbar is closed (the drawing stays on the map).
  // While presenting nothing can be drawn or edited, and the text is drawn larger so it reads from across a room.
  useEffect(() => {
    const active = open && !presenting;
    engineRef.current?.setTool(active ? tool : null);
    if (!active) useDrawStore.getState().setSelectedId(null);
    const map = mapRef.current;
    if (map) setLabelScale(map, presenting ? 1.3 : 1);
  }, [open, tool, presenting, mapRef]);

  // A change to the layers (a name, a note, a new layer, which are shown) is a change to the drawing too.
  const layers = useDrawStore((s) => s.layers);
  const layersSeen = useRef(layers);
  useEffect(() => {
    if (layersSeen.current === layers) return;
    layersSeen.current = layers;
    if (isLoadingDrawing() || isLoadedLayers(layers) || !engineRef.current) return;
    useDrawStore.getState().setDirty(true);
    scheduleDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers]);

  // Hiding or showing a layer takes its shapes off the map or puts them back.
  const hiddenKey = useDrawStore((s) =>
    s.layers
      .filter((l) => !l.visible)
      .map((l) => l.id)
      .sort()
      .join(','),
  );
  useEffect(() => {
    const engine = engineRef.current;
    if (engine) engine.setHiddenLayers(new Set(hiddenKey === '' ? [] : hiddenKey.split(',')));
  }, [hiddenKey]);

  // Units or measuring choices changed: redraw the text.
  useEffect(() => {
    const map = mapRef.current;
    const engine = engineRef.current;
    if (map && engine) showDrawLayers(map, engine.features(), labelOptions(prefs, appUnits));
  }, [prefs, appUnits, mapRef]);

  useEffect(
    () => () => {
      drawController.attach(null);
      window.cancelAnimationFrame(frame.current);
      engineRef.current?.destroy();
      engineRef.current = null;
    },
    [],
  );
}
