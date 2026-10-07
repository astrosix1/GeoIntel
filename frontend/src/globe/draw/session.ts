import { useDrawStore } from '../../state/drawStore';
import { clearDraft, DEFAULT_NAME, saveDraft } from './draft';
import { controllerFeatures, drawController } from './controller';
import { buildDrawing, parseDrawing } from './drawfile';
import type { DrawingData, ParseError } from './drawfile';
import { makeLayer } from './drawlayers';
import type { DrawFeature } from './engine';

// What the drawing panel does to the drawing as a whole, in one place: reading it out of the engine and the layer list, putting
// a saved or imported one in, and starting a new one. (The engine and the store are the two halves of a drawing: the engine
// holds the shapes, the store holds the layers and the name.)

// The drawing as it is now, ready to save or export.
export function currentDrawing(): DrawingData {
  return buildDrawing(controllerFeatures(), useDrawStore.getState().layers);
}

// True while a drawing is being put in place, so that is not counted as the user changing it (it would mark the drawing unsaved).
let loading = false;
export const isLoadingDrawing = () => loading;
// The layer list that was just put in place by a load; React notices it a moment later, when the flag above is already off.
let loadedLayers: unknown = null;
export const isLoadedLayers = (layers: unknown) => layers === loadedLayers;

export interface LoadResult {
  added: number;
  rejected: number;
  skipped: number;
}

// Puts a saved or imported drawing on the map in place of the current one. `drawing` says what it is called and where it came
// from. Returns false (and changes nothing) if the data is not a drawing.
export function openDrawing(data: unknown, drawing: { id: string | null; name: string }, dirty: boolean): { ok: true; result: LoadResult } | { ok: false; error: ParseError } {
  const read = parseDrawing(data);
  if (!read.ok) return read;
  const store = useDrawStore.getState();
  loading = true;
  let counts: { added: number; rejected: number };
  try {
    loadedLayers = read.drawing.data.layers;
    store.setLayers(read.drawing.data.layers);
    counts = drawController.load(read.drawing.data.features as unknown as DrawFeature[]);
  } finally {
    loading = false;
  }
  const { added, rejected } = counts;
  store.setDrawing(drawing);
  store.setDirty(dirty);
  // A load is not counted as an edit (so it does not autosave), so the draft is brought up to date here.
  saveDraft({ drawing, data: currentDrawing(), dirty });
  return { ok: true, result: { added, rejected, skipped: read.drawing.skipped } };
}

// An empty drawing with one layer.
export function startNewDrawing(): void {
  const store = useDrawStore.getState();
  const layer = makeLayer('Layer 1');
  loading = true;
  try {
    loadedLayers = [layer];
    store.setLayers(loadedLayers as typeof store.layers);
    drawController.load([]);
  } finally {
    loading = false;
  }
  store.setDrawing({ id: null, name: DEFAULT_NAME });
  store.setDirty(false);
  clearDraft();
}
