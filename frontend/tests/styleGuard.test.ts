// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { cleanTheme, DEFAULT_THEME, loadTheme, resolveTheme, saveTheme } from '../src/ui/theme.ts';
// @ts-expect-error plain JavaScript module without type declarations
import { checkCss } from '../scripts/check-styles.mjs';

const rules = (css: string): string[] => checkCss(css).map((p: { rule: string }) => p.rule);

describe('style guard', () => {
  it('accepts a stylesheet that only uses tokens', () => {
    const css = `
      .a { color: var(--text); background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-2); }
      .b { font-size: var(--font-3); padding: var(--space-2) var(--space-3); box-shadow: var(--shadow-pop); }
      .c { background: transparent; color: inherit; border-radius: 0; outline: 2px solid var(--focus); }
      .d { border-radius: 50%; border-radius: var(--radius-pill); }
    `;
    assert.deepEqual(rules(css), []);
  });

  it('flags hard-coded colours of every kind', () => {
    assert.equal(rules('.a { color: #fff; }').length, 1);
    assert.equal(rules('.a { background: #0a0e14; }').length, 1);
    assert.equal(rules('.a { background: rgba(0, 0, 0, 0.5); }').length, 1);
    assert.equal(rules('.a { color: hsl(10 20% 30%); }').length, 1);
    assert.match(rules('.a { color: white; }')[0], /named colour/);
    assert.match(rules('.a { border: 1px solid red; }')[0], /named colour/);
  });

  it('flags font sizes outside the scale, in any unit', () => {
    assert.match(rules('.a { font-size: 12.5px; }')[0], /font size outside the scale/);
    assert.match(rules('.a { font-size: 1rem; }')[0], /font size outside the scale/);
    assert.match(rules('.a { font-size: 18px; }')[0], /font size/);
    assert.deepEqual(rules('.a { font-size: var(--font-6); }'), []);
    assert.match(rules('.a { font-size: var(--font-9); }')[0], /font size/);
  });

  it('flags radii outside the scale', () => {
    assert.match(rules('.a { border-radius: 8px; }')[0], /radius outside the scale/);
    assert.match(rules('.a { border-top-left-radius: 10px; }')[0], /radius/);
    assert.deepEqual(rules('.a { border-radius: var(--radius-1) var(--radius-1) 0 0; }'), []);
  });

  it('ignores colours and sizes written in comments and reports the right line', () => {
    const css = '/* panel is #0a0e14, text 12.5px */\n.a {\n  color: var(--text);\n  background: #123456;\n}\n';
    const problems = checkCss(css);
    assert.equal(problems.length, 1);
    assert.equal(problems[0].line, 4);
  });

  it('does not mistake a word inside a class name or custom property for a colour', () => {
    assert.deepEqual(rules('.redAlert { color: var(--alert-red); }'), []);
    assert.deepEqual(rules('.a { --sev-green: var(--sev-1); }'), []);
  });
});

describe('theme choice', () => {
  it('defaults to dark and cleans anything unknown', () => {
    assert.equal(DEFAULT_THEME, 'dark');
    for (const bad of [null, undefined, '', 'blue', 5, {}, 'LIGHT']) assert.equal(cleanTheme(bad), 'dark');
    for (const good of ['dark', 'light', 'system'] as const) assert.equal(cleanTheme(good), good);
  });

  it('"match my system" follows the system, the others ignore it', () => {
    assert.equal(resolveTheme('system', true), 'light');
    assert.equal(resolveTheme('system', false), 'dark');
    assert.equal(resolveTheme('dark', true), 'dark');
    assert.equal(resolveTheme('light', false), 'light');
  });

  it('survives storage that throws, and round-trips through storage', () => {
    const real = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    try {
      Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked'); } });
      assert.equal(loadTheme(), 'dark');
      assert.doesNotThrow(() => saveTheme('light'));
      const store = new Map<string, string>();
      Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
      });
      saveTheme('light');
      assert.equal(loadTheme(), 'light');
      store.set('geointel.theme', 'garbage');
      assert.equal(loadTheme(), 'dark');
    } finally {
      if (real) Object.defineProperty(globalThis, 'localStorage', real);
      else delete (globalThis as Record<string, unknown>).localStorage;
    }
  });
});
