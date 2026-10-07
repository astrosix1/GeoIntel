// Run with: npm test
import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import { cleanDrawPrefs, DEFAULT_DRAW_PREFS, loadDrawPrefs, saveDrawPrefs } from '../src/globe/draw/prefs.ts';

describe('drawing preferences', () => {
  const real = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  afterEach(() => {
    if (real) Object.defineProperty(globalThis, 'localStorage', real);
    else delete (globalThis as Record<string, unknown>).localStorage;
  });

  it('defaults to automatic units with the extra labels off', () => {
    assert.deepEqual(DEFAULT_DRAW_PREFS, { units: 'auto', segments: false, angles: false, bearings: false });
  });

  it('keeps recognised values and falls back field by field on anything else', () => {
    assert.deepEqual(cleanDrawPrefs({ units: 'nautical', segments: true, angles: true, bearings: false }), {
      units: 'nautical', segments: true, angles: true, bearings: false,
    });
    assert.deepEqual(cleanDrawPrefs({ units: 'parsecs', segments: 'yes', angles: 1 }), DEFAULT_DRAW_PREFS);
    for (const junk of [null, undefined, 5, 'x', []]) assert.deepEqual(cleanDrawPrefs(junk), DEFAULT_DRAW_PREFS);
  });

  it('round-trips through storage and ignores corrupt data', () => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    });
    assert.deepEqual(loadDrawPrefs(), DEFAULT_DRAW_PREFS);
    saveDrawPrefs({ units: 'imperial', segments: true, angles: false, bearings: true });
    assert.deepEqual(loadDrawPrefs(), { units: 'imperial', segments: true, angles: false, bearings: true });
    store.set('geointel.draw', '{not json');
    assert.deepEqual(loadDrawPrefs(), DEFAULT_DRAW_PREFS);
  });

  it('survives storage that throws', () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked'); } });
    assert.deepEqual(loadDrawPrefs(), DEFAULT_DRAW_PREFS);
    assert.doesNotThrow(() => saveDrawPrefs(DEFAULT_DRAW_PREFS));
  });
});
