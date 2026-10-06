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

import { cleanMapView, DEFAULT_MAP_VIEW, loadMapView, saveMapView } from '../src/ui/preferences.ts';
import { flatZoomFor } from '../src/globe/fitGlobe.ts';

describe('the map view preference', () => {
  it('defaults to the globe and rejects anything unknown', () => {
    assert.equal(DEFAULT_MAP_VIEW, 'globe');
    assert.equal(cleanMapView('flat'), 'flat');
    assert.equal(cleanMapView('mercator'), 'globe');
    assert.equal(cleanMapView(null), 'globe');
  });

  it('is remembered, ignores corrupt data, and survives blocked storage', () => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    });
    saveMapView('flat');
    assert.equal(loadMapView(), 'flat');
    store.set('geointel.mapview', 'garbage');
    assert.equal(loadMapView(), 'globe');
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked'); } });
    assert.equal(loadMapView(), 'globe');
    assert.doesNotThrow(() => saveMapView('flat'));
    delete (globalThis as Record<string, unknown>).localStorage;
  });
});

describe('fitting the flat map', () => {
  it('fits the whole world width in a wide box and the height in a tall one', () => {
    // 1024 px wide is one zoom level above a 512 px world (minus the 2% margin).
    const wide = flatZoomFor(1024, 2000);
    assert.ok(wide > 0.9 && wide < 1, `wide box zoom ${wide}`);
    // Short and wide: the height limits it, so it zooms out below the width fit.
    assert.ok(flatZoomFor(1024, 300) < wide);
  });

  it('never returns NaN for a collapsed box', () => {
    assert.ok(Number.isFinite(flatZoomFor(0, 0)));
  });
});
