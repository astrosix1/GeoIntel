// Run with: npm test
import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import { buildDrawing } from '../src/globe/draw/drawfile.ts';
import { clearDraft, DEFAULT_NAME, DRAFT_KEY, loadDraft, parseDraft, saveDraft, serializeDraft } from '../src/globe/draw/draft.ts';

const layers = [{ id: 'a', name: 'Layer 1', visible: true, note: '' }];
const point = (id: string) => ({ id, geometry: { type: 'Point', coordinates: [1, 2] }, properties: { mode: 'point', label: 'P' } });
const draft = (n = 1, id: string | null = null, name = 'Plan') => ({
  drawing: { id, name },
  data: buildDrawing(Array.from({ length: n }, (_, i) => point(`p${i}`)), layers),
});

describe('drawing draft', () => {
  const real = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  afterEach(() => {
    if (real) Object.defineProperty(globalThis, 'localStorage', real);
    else delete (globalThis as Record<string, unknown>).localStorage;
  });
  const fakeStorage = () => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) },
    });
    return store;
  };

  it('round-trips through storage with the saved drawing it came from', () => {
    fakeStorage();
    const id = '0a9173c2-fdb6-4a64-80be-caf59fd02940';
    saveDraft(draft(2, id, 'Gulf'));
    const back = loadDraft();
    assert.ok(back);
    assert.deepEqual(back!.drawing, { id, name: 'Gulf' });
    assert.equal(back!.data.features.length, 2);
    assert.equal(back!.data.features[0].properties.label, 'P');
  });

  it('does not keep an empty drawing, and removes an old draft when the drawing is emptied', () => {
    const store = fakeStorage();
    saveDraft(draft(1));
    assert.ok(store.has(DRAFT_KEY));
    saveDraft(draft(0));
    assert.ok(!store.has(DRAFT_KEY));
    assert.equal(loadDraft(), null);
  });

  it('ignores corrupt or hostile stored data', () => {
    const store = fakeStorage();
    for (const junk of ['{not json', 'null', '"x"', '{"data":5}', '{"data":{"type":"FeatureCollection","features":[]}}', '[]']) {
      store.set(DRAFT_KEY, junk);
      assert.equal(loadDraft(), null, junk);
    }
  });

  it('falls back to a default name and no saved id when those are missing or odd', () => {
    const text = JSON.stringify({ id: 'not-a-uuid', name: '   ', data: draft(1).data });
    const back = parseDraft(text);
    assert.ok(back);
    assert.deepEqual(back!.drawing, { id: null, name: DEFAULT_NAME });
  });

  it('refuses a draft that is too big to keep', () => {
    const big = draft(1);
    big.data.features[0].properties.note = 'x'.repeat(2000);
    big.data.features = Array.from({ length: 480 }, () => big.data.features[0]);
    assert.equal(serializeDraft(big), null);
  });

  it('survives storage that throws', () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked'); } });
    assert.equal(loadDraft(), null);
    assert.doesNotThrow(() => saveDraft(draft(1)));
    assert.doesNotThrow(() => clearDraft());
  });

  it('clears the draft', () => {
    const store = fakeStorage();
    saveDraft(draft(1));
    clearDraft();
    assert.ok(!store.has(DRAFT_KEY));
  });
});
