import { create } from 'zustand';
import type { DrawTool } from '../globe/draw/engine';
import { cleanLayerName, cleanLayerNote, makeLayer, MAX_LAYERS, nextLayerName, soloLayers } from '../globe/draw/drawlayers';
import type { DrawLayer } from '../globe/draw/drawlayers';
import { loadDrawPrefs, saveDrawPrefs } from '../globe/draw/prefs';
import type { DrawPrefs } from '../globe/draw/prefs';
import { DEFAULT_NAME } from '../globe/draw/draft';

// State of the drawing tool that the interface needs: whether it is open, which tool is chosen, what can be undone, and
// what is selected. The drawing itself lives in the engine (globe/draw/engine.ts), not here.
interface DrawState {
  open: boolean;
  tool: DrawTool;
  canUndo: boolean;
  canRedo: boolean;
  selectedId: string | null;
  shapeCount: number;
  // Goes up on every change to the drawing, so panels that show the selected shape know to read it again.
  revision: number;
  bumpRevision: () => void;
  // The drawing's layers, and the one new shapes go on.
  layers: DrawLayer[];
  activeLayerId: string;
  addLayer: () => string | null;
  renameLayer: (id: string, name: string) => void;
  setLayerNote: (id: string, note: string) => void;
  toggleLayer: (id: string) => void;
  soloLayer: (id: string) => void;
  setActiveLayer: (id: string) => void;
  // Removes a layer from the list (never the last one). Its shapes are removed by the caller first.
  removeLayer: (id: string) => void;
  // The drawing being worked on: the saved drawing it came from (null when it has never been saved), its name, and whether
  // it has changed since it was last saved or opened.
  drawing: { id: string | null; name: string };
  dirty: boolean;
  setDrawing: (drawing: { id: string | null; name: string }) => void;
  setDirty: (dirty: boolean) => void;
  // Replaces the layers wholesale (opening or restoring a drawing); the first one becomes the active layer.
  setLayers: (layers: DrawLayer[]) => void;
  // What the tool measures and shows (remembered in this browser).
  prefs: DrawPrefs;
  setPrefs: (change: Partial<DrawPrefs>) => void;
  setOpen: (open: boolean) => void;
  setTool: (tool: DrawTool) => void;
  setHistory: (state: { canUndo: boolean; canRedo: boolean }) => void;
  setSelectedId: (id: string | null) => void;
  setShapeCount: (count: number) => void;
}

const firstLayer = makeLayer('Layer 1');

export const useDrawStore = create<DrawState>((set, get) => ({
  open: false,
  tool: 'select',
  canUndo: false,
  canRedo: false,
  selectedId: null,
  shapeCount: 0,
  revision: 0,
  bumpRevision: () => set((state) => ({ revision: state.revision + 1 })),
  layers: [firstLayer],
  activeLayerId: firstLayer.id,
  addLayer: () => {
    const { layers } = get();
    if (layers.length >= MAX_LAYERS) return null;
    const layer = makeLayer(nextLayerName(layers));
    set({ layers: [...layers, layer], activeLayerId: layer.id });
    return layer.id;
  },
  renameLayer: (id, name) =>
    set((state) => ({ layers: state.layers.map((l, i) => (l.id === id ? { ...l, name: cleanLayerName(name, `Layer ${i + 1}`) } : l)) })),
  setLayerNote: (id, note) => set((state) => ({ layers: state.layers.map((l) => (l.id === id ? { ...l, note: cleanLayerNote(note) } : l)) })),
  toggleLayer: (id) => set((state) => ({ layers: state.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)) })),
  soloLayer: (id) => set((state) => ({ layers: soloLayers(state.layers, id), activeLayerId: id })),
  // Choosing the layer to draw on also shows it, so what is drawn next is never invisible.
  setActiveLayer: (id) =>
    set((state) => ({ activeLayerId: id, layers: state.layers.map((l) => (l.id === id ? { ...l, visible: true } : l)) })),
  removeLayer: (id) =>
    set((state) => {
      if (state.layers.length <= 1) return {};
      const layers = state.layers.filter((l) => l.id !== id);
      return { layers, activeLayerId: state.activeLayerId === id ? layers[0].id : state.activeLayerId };
    }),
  drawing: { id: null, name: DEFAULT_NAME },
  dirty: false,
  setDrawing: (drawing) => set({ drawing }),
  setDirty: (dirty) => set({ dirty }),
  setLayers: (layers) => set({ layers, activeLayerId: layers[0].id }),
  prefs: loadDrawPrefs(),
  setPrefs: (change) =>
    set((state) => {
      const prefs = { ...state.prefs, ...change };
      saveDrawPrefs(prefs);
      return { prefs };
    }),
  setOpen: (open) => set({ open }),
  setTool: (tool) => set({ tool }),
  setHistory: ({ canUndo, canRedo }) => set({ canUndo, canRedo }),
  setSelectedId: (id) => set({ selectedId: id }),
  setShapeCount: (count) => set({ shapeCount: count }),
}));

// True while the drawing tool is open: map clicks then belong to the tool, so pins, countries and zones must not react.
export function isDrawingOpen(): boolean {
  return useDrawStore.getState().open;
}
