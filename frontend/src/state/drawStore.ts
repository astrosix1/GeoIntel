import { create } from 'zustand';
import type { DrawTool } from '../globe/draw/engine';
import { loadDrawPrefs, saveDrawPrefs } from '../globe/draw/prefs';
import type { DrawPrefs } from '../globe/draw/prefs';

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
  // What the tool measures and shows (remembered in this browser).
  prefs: DrawPrefs;
  setPrefs: (change: Partial<DrawPrefs>) => void;
  setOpen: (open: boolean) => void;
  setTool: (tool: DrawTool) => void;
  setHistory: (state: { canUndo: boolean; canRedo: boolean }) => void;
  setSelectedId: (id: string | null) => void;
  setShapeCount: (count: number) => void;
}

export const useDrawStore = create<DrawState>((set) => ({
  open: false,
  tool: 'select',
  canUndo: false,
  canRedo: false,
  selectedId: null,
  shapeCount: 0,
  revision: 0,
  bumpRevision: () => set((state) => ({ revision: state.revision + 1 })),
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
