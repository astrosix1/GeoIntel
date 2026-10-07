import { bearingBetween } from './measure.ts';
import type { Position } from './measure.ts';
import { colorOf } from './style.ts';

// The arrowhead for each Arrow shape: where it goes (the arrow's end), which way it points (the bearing of the last
// segment, so it follows the great circle) and its colour. The head itself is a map symbol drawn by layers.ts. This file
// imports only pure modules so it can be unit-tested (frontend/tests/arrows.test.ts).
export interface ArrowHead {
  id: string;
  position: Position;
  bearing: number;
  color: string;
}

export function arrowHeads(features: { id?: string | number; geometry: { type: string; coordinates: unknown }; properties?: Record<string, unknown> | null }[]): ArrowHead[] {
  const heads: ArrowHead[] = [];
  for (const feature of features) {
    if (feature.properties?.mode !== 'arrow' || feature.geometry.type !== 'LineString') continue;
    const coords = feature.geometry.coordinates as Position[];
    if (coords.length < 2) continue;
    const from = coords[coords.length - 2];
    const to = coords[coords.length - 1];
    if (from[0] === to[0] && from[1] === to[1]) continue; // no direction yet
    heads.push({ id: String(feature.id ?? ''), position: to, bearing: bearingBetween(from, to), color: colorOf(feature.properties) });
  }
  return heads;
}
