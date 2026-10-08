// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { changeText, formatCompact, formatNumber, sparklinePath } from '../src/sidebars/analysis/country/chart.ts';

describe('sparklinePath', () => {
  it('draws nothing for fewer than two points', () => {
    assert.equal(sparklinePath([], 100, 20), '');
    assert.equal(sparklinePath([[2020, 1]], 100, 20), '');
  });

  it('runs left to right over the years and bottom to top over the values', () => {
    const path = sparklinePath([[2000, 0], [2010, 10]], 102, 22, 2);
    assert.equal(path, 'M2.0 20.0 L100.0 2.0');
  });

  it('does not divide by zero for a flat line or a single year', () => {
    assert.match(sparklinePath([[2000, 5], [2001, 5]], 100, 20), /^M[\d.]+ [\d.]+ L[\d.]+ [\d.]+$/);
    assert.doesNotMatch(sparklinePath([[2000, 5], [2000, 6]], 100, 20), /NaN/);
  });
});

describe('formatNumber', () => {
  it('groups thousands and fixes the decimals', () => {
    assert.equal(formatNumber(68000000, 0), '68,000,000');
    assert.equal(formatNumber(82.9804878, 1), '83.0');
    assert.equal(formatNumber(2.7, 2), '2.70');
  });
});

describe('changeText', () => {
  it('says up or down in percent, with the starting year', () => {
    assert.equal(changeText([[1995, 100], [2024, 150]]), 'up 50% since 1995');
    assert.equal(changeText([[1990, 80], [2024, 76]]), 'down 5.0% since 1990');
  });

  it('says little changed for a tiny move', () => {
    assert.equal(changeText([[2000, 100], [2020, 100.2]]), 'little changed since 2000');
  });

  it('moves percentages and rates in points, not in percent of a percent', () => {
    assert.equal(changeText([[1991, 5], [2024, 2.5]], '% a year'), 'down 2.5 points since 1991');
    assert.equal(changeText([[1990, 60], [2024, 70]], '% of total'), 'up 10.0 points since 1990');
    assert.equal(changeText([[2000, 5], [2020, 5.01]], '% a year'), 'little changed since 2000');
  });

  it('gives only the start when the series touches zero or goes negative', () => {
    assert.equal(changeText([[1983, 0.5], [1990, -2], [2025, 4.5]], 'US$', 1), 'was 0.5 in 1983');
  });

  it('has nothing to say for one point', () => {
    assert.equal(changeText([[2000, 1]]), null);
  });
});

describe('formatCompact', () => {
  it('shortens big figures', () => {
    assert.equal(formatCompact(3366300000000), '3.37T');
    assert.equal(formatCompact(68720337), '68.72M');
    assert.equal(formatCompact(950), '950');
  });
});
