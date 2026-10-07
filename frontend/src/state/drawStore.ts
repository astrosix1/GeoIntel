import { create } from 'zustand';
import type { DrawTool } from '../globe/draw/engine';

// State of the drawing tool that the interface needs: whether it is open, which tool is chosen, what can be undone, and
// what is selected. The drawing itself lives in the engine (globe/draw/engine.ts), not here.
interface DrawState {
  open: boolean;
  tool: DrawTool;
  canUndo: boolean;
  canRedo: boolean;
  selectedId: string | null;
  shapeCount: number;
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
