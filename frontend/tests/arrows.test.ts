// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { arrowHeads } from '../src/globe/draw/arrows.ts';

const arrow = (id: string, coordinates: [number, number][], props: Record<string, unknown> = {}) => ({
  id,
  properties: { mode: 'arrow', ...props },
  geometry: { type: 'LineString', coordinates },
});

describe('arrowheads', () => {
  it('puts the head at the end of the arrow, pointing along its last segment', () => {
    const [head] = arrowHeads([arrow('a', [[0, 0], [0, 1]])]);
    assert.deepEqual(head.position, [0, 1]);
    assert.ok(Math.abs(head.bearing - 0) < 0.001, `bearing ${head.bearing}`);
    const [east] = arrowHeads([arrow('b', [[0, 0], [1, 0]])]);
    assert.ok(Math.abs(east.bearing - 90) < 0.001);
  });

  it('uses the shape colour, or the default blue', () => {
    assert.equal(arrowHeads([arrow('a', [[0, 0], [1, 0]], { color: '#ef4444' })])[0].color, '#ef4444');
    assert.equal(arrowHeads([arrow('a', [[0, 0], [1, 0]])])[0].color, '#3b82f6');
  });

  it('only draws heads for arrows with a direction', () => {
    assert.deepEqual(arrowHeads([arrow('a', [[0, 0]]), arrow('b', [[5, 5], [5, 5]])]), []);
  });

  it('ignores every other kind of shape', () => {
    const line = { id: 'l', properties: { mode: 'linestring' }, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } };
    const polygon = { id: 'p', properties: { mode: 'arrow' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } };
    assert.deepEqual(arrowHeads([line, polygon]), []);
  });
});
