// The named layers of a drawing ("Scenario A: blockade", "Evacuation route"). Every shape belongs to one layer; a layer can
// be shown or hidden on its own so outcomes can be compared side by side. This file imports nothing so it can be
// unit-tested (frontend/tests/drawlayers.test.ts).

export interface DrawLayer {
  id: string;
  name: string;
  visible: boolean;
  note: string;
}

export const MAX_LAYERS = 20;
export const MAX_LAYER_NAME = 60;
export const MAX_LAYER_NOTE = 2000;

const ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

// A fresh id for a layer.
export function newLayerId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `layer-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function makeLayer(name: string, id: string = newLayerId()): DrawLayer {
  return { id, name, visible: true, note: '' };
}

// "Layer 1", "Layer 2", ...: the first number not already used as a default name.
export function nextLayerName(layers: DrawLayer[]): string {
  const taken = new Set(layers.map((l) => l.name));
  for (let n = 1; n <= layers.length + 1; n++) {
    const name = `Layer ${n}`;
    if (!taken.has(name)) return name;
  }
  return `Layer ${layers.length + 1}`;
}

// A name cleaned for storing: control characters out, trimmed, cut to the limit; empty falls back to the given default.
export function cleanLayerName(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  // eslint-disable-next-line no-control-regex
  const name = value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, MAX_LAYER_NAME).trim();
  return name === '' ? fallback : name;
}

export function cleanLayerNote(value: unknown): string {
  if (typeof value !== 'string') return '';
  // eslint-disable-next-line no-control-regex
  return value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').slice(0, MAX_LAYER_NOTE);
}

// A list of layers read back from storage (or from a saved drawing): only well-formed entries, no repeated ids, at most
// MAX_LAYERS, and always at least one layer so there is somewhere to draw.
export function cleanLayers(value: unknown): DrawLayer[] {
  const layers: DrawLayer[] = [];
  const seen = new Set<string>();
  if (Array.isArray(value)) {
    for (const item of value) {
      if (layers.length >= MAX_LAYERS) break;
      if (typeof item !== 'object' || item === null) continue;
      const entry = item as Record<string, unknown>;
      if (typeof entry.id !== 'string' || !ID_PATTERN.test(entry.id) || seen.has(entry.id)) continue;
      seen.add(entry.id);
      layers.push({
        id: entry.id,
        name: cleanLayerName(entry.name, `Layer ${layers.length + 1}`),
        visible: entry.visible !== false,
        note: cleanLayerNote(entry.note),
      });
    }
  }
  return layers.length > 0 ? layers : [makeLayer('Layer 1')];
}

// How many shapes each layer holds, given each shape's layer id (a shape with no layer counts for `fallback`).
export function countByLayer(shapeLayers: (string | undefined)[], fallback: string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const layer of shapeLayers) {
    const id = layer ?? fallback;
    counts[id] = (counts[id] ?? 0) + 1;
  }
  return counts;
}

// The ids of the hidden layers.
export function hiddenIds(layers: DrawLayer[]): Set<string> {
  return new Set(layers.filter((l) => !l.visible).map((l) => l.id));
}

// "Show only this layer": every other layer is hidden and this one shown. Asking again (when it is already the only one
// shown) shows everything, so the same button flips between the focused view and the full one.
export function soloLayers(layers: DrawLayer[], id: string): DrawLayer[] {
  const onlyThis = layers.every((l) => l.visible === (l.id === id));
  return layers.map((l) => ({ ...l, visible: onlyThis ? true : l.id === id }));
}
