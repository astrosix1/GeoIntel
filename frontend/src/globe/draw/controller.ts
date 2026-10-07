import type { DrawEngine, DrawFeature } from './engine';
import type { ShapeStyle } from './style';

// Lets the toolbar and the shape panel (React) ask the drawing engine (attached to the map by useDraw) to undo, redo,
// delete, restyle and copy, without holding a reference to the map or the library. Commands are ignored while no engine
// is attached.
let engine: DrawEngine | null = null;

export const drawController = {
  attach(next: DrawEngine | null) {
    engine = next;
  },
  undo: () => engine?.undo(),
  redo: () => engine?.redo(),
  deleteSelected: () => engine?.deleteSelected(),
  clear: () => engine?.clear(),
  selected: (): DrawFeature | null => engine?.selected() ?? null,
  setStyle: (change: Partial<Record<keyof ShapeStyle, unknown>>) => engine?.setStyle(change),
  duplicate: (): boolean => engine?.duplicateSelected() ?? false,
};
