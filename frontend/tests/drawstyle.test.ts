// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  cleanStyle, cleanText, colorOf, dashOf, DEFAULT_COLOR, DEFAULT_FILL, DEFAULT_WIDTH, fillOf, MAX_LABEL_LENGTH, MAX_NOTE_LENGTH, PALETTE, widthOf,
} from '../src/globe/draw/style.ts';

describe('shape style readers', () => {
  it('fall back to the defaults for a shape with no style', () => {
    for (const props of [undefined, null, {}, { color: 5, width: 'x', fill: null, dash: 7 }]) {
      assert.equal(colorOf(props as never), DEFAULT_COLOR);
      assert.equal(widthOf(props as never), DEFAULT_WIDTH);
      assert.equal(fillOf(props as never), DEFAULT_FILL);
      assert.equal(dashOf(props as never), undefined);
    }
  });

  it('read a valid style back', () => {
    assert.equal(colorOf({ color: '#ef4444' }), '#ef4444');
    assert.equal(colorOf({ color: '#EF4444' }), '#ef4444');
    assert.equal(widthOf({ width: 5 }), 5);
    assert.equal(fillOf({ fill: 0 }), 0);
    assert.deepEqual(dashOf({ dash: 'dashed' }), [8, 6]);
    assert.equal(dashOf({ dash: 'solid' }), undefined);
  });

  it('reject colours and sizes outside the palette and the steps', () => {
    assert.equal(colorOf({ color: '#123456' }), DEFAULT_COLOR);
    assert.equal(colorOf({ color: 'red' }), DEFAULT_COLOR);
    assert.equal(widthOf({ width: 4 }), DEFAULT_WIDTH);
    assert.equal(fillOf({ fill: 0.9 }), DEFAULT_FILL);
  });

  it('has a palette of distinct valid colours that leaves out the selection amber', () => {
    const values = PALETTE.map((c) => c.value);
    assert.equal(new Set(values).size, values.length);
    assert.ok(values.every((v) => /^#[0-9a-f]{6}$/.test(v)));
    assert.ok(!values.includes('#f59e0b'));
  });
});

describe('cleaning text and styles for storing', () => {
  it('keeps text, cuts it to the limit and strips control characters', () => {
    assert.equal(cleanText('Evacuation route', MAX_LABEL_LENGTH), 'Evacuation route');
    assert.equal(cleanText('a\u0000b\u0007c\nd', 100), 'abc\nd');
    assert.equal(cleanText('x'.repeat(500), MAX_LABEL_LENGTH)?.length, MAX_LABEL_LENGTH);
    assert.equal(cleanText('y'.repeat(5000), MAX_NOTE_LENGTH)?.length, MAX_NOTE_LENGTH);
  });

  it('drops empty and non-text values', () => {
    for (const value of ['', '   ', null, undefined, 5, {}, []]) assert.equal(cleanText(value, 10), undefined);
  });

  it('does not treat markup as anything but text', () => {
    assert.equal(cleanText('<img src=x onerror=alert(1)>', 100), '<img src=x onerror=alert(1)>');
  });

  it('keeps only known, valid style fields', () => {
    const style = cleanStyle({ color: '#22c55e', width: 5, fill: 0.4, dash: 'dashed', label: ' Zone A ', note: 'n', evil: 'x', __proto__: { a: 1 } });
    assert.deepEqual(style, { color: '#22c55e', width: 5, fill: 0.4, dash: 'dashed', label: ' Zone A ', note: 'n' });
    assert.deepEqual(cleanStyle({ color: '#000000', width: 99, fill: 2, dash: 'dotted', label: '', note: 3 }), {});
  });
});
