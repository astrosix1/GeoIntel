// Run with: npm test
import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import {
  cleanFlag, cleanPanels, DEFAULT_PANELS, DEFAULT_STARFIELD, DOCK_MIN_WIDTH, loadPanels, loadStarfield, savePanels, saveStarfield,
} from '../src/ui/preferences.ts';

describe('interface preferences', () => {
  const real = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  afterEach(() => {
    if (real) Object.defineProperty(globalThis, 'localStorage', real);
    else delete (globalThis as Record<string, unknown>).localStorage;
  });

  it('panels default to docked and any junk falls back to it', () => {
    assert.equal(DEFAULT_PANELS, 'docked');
    for (const bad of [null, undefined, '', 'floating', 5, {}, 'DOCKED']) assert.equal(cleanPanels(bad), 'docked');
    assert.equal(cleanPanels('overlay'), 'overlay');
    assert.equal(cleanPanels('docked'), 'docked');
  });

  it('the starfield defaults to on', () => {
    assert.equal(DEFAULT_STARFIELD, true);
  });

  it('flags read the forms storage can hand back, and fall back otherwise', () => {
    for (const on of [true, 'true', '1']) assert.equal(cleanFlag(on, false), true);
    for (const off of [false, 'false', '0']) assert.equal(cleanFlag(off, true), false);
    for (const odd of [null, undefined, 'yes', 2, {}]) {
      assert.equal(cleanFlag(odd, true), true);
      assert.equal(cleanFlag(odd, false), false);
    }
  });

  it('round-trips through storage and ignores corrupt data', () => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    });
    assert.equal(loadPanels(), 'docked');
    assert.equal(loadStarfield(), true);
    savePanels('overlay');
    saveStarfield(false);
    assert.equal(loadPanels(), 'overlay');
    assert.equal(loadStarfield(), false);
    store.set('geointel.panels', 'garbage');
    store.set('geointel.starfield', 'garbage');
    assert.equal(loadPanels(), 'docked');
    assert.equal(loadStarfield(), true);
  });

  it('survives storage that throws', () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked'); } });
    assert.equal(loadPanels(), 'docked');
    assert.equal(loadStarfield(), true);
    assert.doesNotThrow(() => savePanels('overlay'));
    assert.doesNotThrow(() => saveStarfield(false));
  });

  it('panels dock only on a window wide enough for two panels and a map', () => {
    assert.ok(DOCK_MIN_WIDTH >= 800 && DOCK_MIN_WIDTH <= 1100);
  });
});
