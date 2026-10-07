import type { DrawEngine } from './engine';

// Lets the toolbar (React) ask the drawing engine (attached to the map by useDraw) to undo, redo, delete and clear,
// without the toolbar holding a reference to the map or the library. Commands are ignored while no engine is attached.
let engine: DrawEngine | null = null;

export const drawController = {
  attach(next: DrawEngine | null) {
    engine = next;
  },
  undo: () => engine?.undo(),
  redo: () => engine?.redo(),
  deleteSelected: () => engine?.deleteSelected(),
  clear: () => engine?.clear(),
};
