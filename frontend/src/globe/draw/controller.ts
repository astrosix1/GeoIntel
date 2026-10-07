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
  selectedLayer: (): string | null => engine?.selectedLayer() ?? null,
  moveSelectedToLayer: (layerId: string) => engine?.moveSelectedToLayer(layerId),
  counts: (): Record<string, number> => engine?.counts() ?? {},
  deleteLayerShapes: (layerId: string) => engine?.deleteLayerShapes(layerId),
  allFeatures: (): DrawFeature[] => engine?.allFeatures() ?? [],
  load: (features: DrawFeature[]) => engine?.load(features) ?? { added: 0, rejected: features.length },
  setStyle: (change: Partial<Record<keyof ShapeStyle, unknown>>) => engine?.setStyle(change),
  duplicate: (): boolean => engine?.duplicateSelected() ?? false,
  captureImage: (title: string | null): Promise<Blob | null> => engine?.captureImage(title) ?? Promise.resolve(null),
};

// Every shape in the drawing, hidden layers included, each with its layer id: what is saved.
export function controllerFeatures(): DrawFeature[] {
  return drawController.allFeatures();
}
