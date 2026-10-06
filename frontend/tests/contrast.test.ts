// Run with: npm test
// Reads src/styles/tokens.css and checks the contrast of every pair that matters, in both themes:
// 4.5:1 for text, 3:1 for marks, focus rings and control edges.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

type Rgba = [number, number, number, number];
type Tokens = Record<string, string>;

const css = readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8');

function block(selector: string): Tokens {
  const start = css.indexOf(selector);
  assert.ok(start >= 0, `no ${selector} block in tokens.css`);
  const open = css.indexOf('{', start);
  const close = css.indexOf('\n}', open);
  const tokens: Tokens = {};
  for (const match of css.slice(open, close).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) tokens[match[1]] = match[2].trim();
  return tokens;
}

const dark = block(':root {');
const light = { ...dark, ...block(":root[data-theme='light']") };

function parse(value: string): Rgba {
  const hex = /^#([0-9a-f]{6})$/i.exec(value);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  const rgba = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(value);
  assert.ok(rgba, `cannot read colour "${value}"`);
  return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3]), rgba[4] === undefined ? 1 : Number(rgba[4])];
}

// A colour drawn over a solid background.
function over(top: Rgba, base: Rgba): Rgba {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + base[i] * (1 - a)).concat(1) as Rgba;
}

function luminance([r, g, b]: Rgba): number {
  const f = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function check(theme: Tokens, name: string) {
  const colour = (token: string) => parse(theme[token] ?? assert.fail(`missing ${token}`));
  const panel = colour('--panel');
  const raised = over(colour('--raised'), panel);
  const strong = over(colour('--raised-strong'), panel);
  const onPanel = (token: string) => over(colour(token), panel);

  describe(`${name} theme`, () => {
    it('text is readable on the panel and on hovered rows', () => {
      for (const token of ['--text', '--text-2', '--text-3']) {
        const onP = ratio(over(colour(token), panel), panel);
        assert.ok(onP >= 4.5, `${token} on panel is ${onP.toFixed(2)}:1`);
        const onR = ratio(over(colour(token), raised), raised);
        assert.ok(onR >= 4.5, `${token} on a raised row is ${onR.toFixed(2)}:1`);
        const onS = ratio(over(colour(token), strong), strong);
        assert.ok(onS >= 4.5, `${token} on a hovered row is ${onS.toFixed(2)}:1`);
      }
    });

    it('accent, sky and warning colours work as text on the panel', () => {
      for (const token of ['--accent', '--sky', '--warn']) {
        const r = ratio(onPanel(token), panel);
        assert.ok(r >= 4.5, `${token} on panel is ${r.toFixed(2)}:1`);
      }
    });

    it('a primary button\'s text is readable on the accent', () => {
      const r = ratio(colour('--accent-fg'), colour('--accent'));
      assert.ok(r >= 4.5, `accent-fg on accent is ${r.toFixed(2)}:1`);
    });

    it('text on every severity fill is readable', () => {
      for (const level of [1, 2, 3, 4, 5]) {
        const r = ratio(colour(`--sev-${level}-fg`), colour(`--sev-${level}`));
        assert.ok(r >= 4.5, `severity ${level} text is ${r.toFixed(2)}:1`);
      }
    });

    it('text on every alert fill is readable', () => {
      for (const level of ['red', 'orange', 'green']) {
        const r = ratio(colour(`--alert-${level}-fg`), colour(`--alert-${level}`));
        assert.ok(r >= 4.5, `alert ${level} text is ${r.toFixed(2)}:1`);
      }
    });

    it('severity and alert marks are visible against the panel (3:1)', () => {
      const tokens = [1, 2, 3, 4, 5].map((n) => `--sev-${n}-mark`).concat(['red', 'orange', 'green'].map((l) => `--alert-${l}-mark`));
      for (const token of tokens) {
        const r = ratio(colour(token), panel);
        assert.ok(r >= 3, `${token} on panel is ${r.toFixed(2)}:1`);
      }
    });

    it('control edges and the focus ring are visible (3:1)', () => {
      const edge = ratio(onPanel('--edge-control'), panel);
      assert.ok(edge >= 3, `control edge is ${edge.toFixed(2)}:1`);
      const focus = ratio(colour('--focus'), panel);
      assert.ok(focus >= 3, `focus ring is ${focus.toFixed(2)}:1`);
    });

    it('text on the soft cell fills of the meeting planner is readable', () => {
      for (const token of ['--ok-soft', '--caution-soft']) {
        const fill = over(colour(token), panel);
        const r = ratio(over(colour('--text'), fill), fill);
        assert.ok(r >= 4.5, `text on ${token} is ${r.toFixed(2)}:1`);
      }
    });

    it('the overlay panel stays readable over a bright map', () => {
      const bright: Rgba = [255, 255, 255, 1];
      const overlay = over(colour('--panel-overlay'), bright);
      const r = ratio(over(colour('--text-2'), overlay), overlay);
      assert.ok(r >= 4.5, `secondary text on the overlay over white is ${r.toFixed(2)}:1`);
    });
  });
}

describe('tokens file', () => {
  it('defines every token the light theme overrides in the dark block too', () => {
    for (const token of Object.keys(block(":root[data-theme='light']"))) assert.ok(token in dark, `${token} is only in the light theme`);
  });

  it('uses only the six type sizes, two radii and the 4 px spacing grid', () => {
    const sizes = ['--font-1', '--font-2', '--font-3', '--font-4', '--font-5', '--font-6'].map((t) => dark[t]);
    assert.deepEqual(sizes, ['11px', '12px', '13px', '14px', '16px', '20px']);
    assert.deepEqual([dark['--radius-1'], dark['--radius-2']], ['3px', '6px']);
    for (const t of ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5']) assert.equal(parseInt(dark[t]) % 4, 0, t);
  });
});

check(dark, 'dark');
check(light, 'light');
