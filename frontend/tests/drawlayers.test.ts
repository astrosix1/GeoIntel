// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  cleanLayerName, cleanLayerNote, cleanLayers, countByLayer, hiddenIds, makeLayer, MAX_LAYER_NAME, MAX_LAYERS, nextLayerName, newLayerId, soloLayers,
} from '../src/globe/draw/drawlayers.ts';

const layer = (id: string, name = id, visible = true) => ({ id, name, visible, note: '' });

describe('layer names', () => {
  it('numbers new layers from the first unused default name', () => {
    assert.equal(nextLayerName([]), 'Layer 1');
    assert.equal(nextLayerName([layer('a', 'Layer 1')]), 'Layer 2');
    assert.equal(nextLayerName([layer('a', 'Layer 2'), layer('b', 'Blockade')]), 'Layer 1');
    assert.equal(nextLayerName([layer('a', 'Layer 1'), layer('b', 'Layer 2'), layer('c', 'Layer 3')]), 'Layer 4');
  });

  it('cleans a name for storing and falls back when it is empty or not text', () => {
    assert.equal(cleanLayerName('  Scenario A  ', 'x'), 'Scenario A');
    assert.equal(cleanLayerName('a\u0000b\nc', 'x'), 'a b c');
    assert.equal(cleanLayerName('n'.repeat(500), 'x').length, MAX_LAYER_NAME);
    for (const bad of ['', '   ', null, undefined, 4, {}]) assert.equal(cleanLayerName(bad, 'Layer 9'), 'Layer 9');
  });

  it('keeps note text, cut to the limit and without control characters', () => {
    assert.equal(cleanLayerNote('Plan B\nif the road closes'), 'Plan B\nif the road closes');
    assert.equal(cleanLayerNote('a\u0000b'), 'ab');
    assert.equal(cleanLayerNote(7), '');
  });

  it('makes distinct ids', () => {
    assert.notEqual(newLayerId(), newLayerId());
    assert.equal(makeLayer('X', 'id1').visible, true);
  });
});

describe('reading layers back from storage', () => {
  it('keeps well-formed layers in order', () => {
    const out = cleanLayers([{ id: 'a', name: 'One', visible: false, note: 'n' }, { id: 'b', name: 'Two' }]);
    assert.deepEqual(out, [
      { id: 'a', name: 'One', visible: false, note: 'n' },
      { id: 'b', name: 'Two', visible: true, note: '' },
    ]);
  });

  it('drops malformed entries and repeated ids', () => {
    const out = cleanLayers([null, 5, { name: 'no id' }, { id: 'bad id!', name: 'x' }, { id: 'a', name: 'A' }, { id: 'a', name: 'A again' }]);
    assert.deepEqual(out.map((l) => l.id), ['a']);
  });

  it('always leaves at least one layer', () => {
    for (const junk of [undefined, null, [], 'x', 3, [{}]]) {
      const out = cleanLayers(junk);
      assert.equal(out.length, 1);
      assert.equal(out[0].name, 'Layer 1');
    }
  });

  it('caps the number of layers', () => {
    const many = Array.from({ length: MAX_LAYERS + 10 }, (_, i) => ({ id: `l${i}`, name: `L${i}` }));
    assert.equal(cleanLayers(many).length, MAX_LAYERS);
  });
});

describe('counting and hiding', () => {
  it('counts shapes per layer, putting unassigned shapes on the fallback layer', () => {
    assert.deepEqual(countByLayer(['a', 'a', 'b', undefined], 'a'), { a: 3, b: 1 });
    assert.deepEqual(countByLayer([], 'a'), {});
  });

  it('lists the hidden layers', () => {
    assert.deepEqual([...hiddenIds([layer('a'), layer('b', 'B', false), layer('c', 'C', false)])].sort(), ['b', 'c']);
  });

  it('shows only one layer, and a second ask shows them all again', () => {
    const all = [layer('a'), layer('b'), layer('c')];
    const solo = soloLayers(all, 'b');
    assert.deepEqual(solo.map((l) => l.visible), [false, true, false]);
    assert.deepEqual(soloLayers(solo, 'b').map((l) => l.visible), [true, true, true]);
    assert.deepEqual(soloLayers(solo, 'c').map((l) => l.visible), [false, false, true]);
  });
});
