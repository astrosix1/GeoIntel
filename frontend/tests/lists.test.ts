// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { defaultDirection, DEFAULT_CRISIS_SORT, sortCrises } from '../src/lib/filters.ts';
import { shortAge } from '../src/lib/time.ts';
import { severityTone } from '../src/globe/severity.ts';

const crisis = (id: string, severity: number, date: string, country: string) =>
  ({ id, title: id, severity, date, country, type: 'x', scope: 'global', lat: 0, lon: 0, source_url: '' }) as never;

const ids = (list: ReturnType<typeof sortCrises>) => list.map((c) => c.id).join(',');

describe('sorting the events list', () => {
  const list = [
    crisis('a', 40, '2026-10-05T10:00:00', 'Peru'),
    crisis('b', 90, '2026-10-05T09:00:00', 'Chad'),
    crisis('c', 40, '2026-10-05T12:00:00', 'Peru'),
    crisis('d', 10, '2026-10-05T11:00:00', 'Albania'),
  ];

  it('severity, most severe first, ties newest first (the default, matching the server)', () => {
    assert.deepEqual(DEFAULT_CRISIS_SORT, { key: 'severity', dir: 'desc' });
    assert.equal(ids(sortCrises(list, DEFAULT_CRISIS_SORT)), 'b,c,a,d');
  });

  it('severity ascending flips it, ties still newest first', () => {
    assert.equal(ids(sortCrises(list, { key: 'severity', dir: 'asc' })), 'd,c,a,b');
  });

  it('newest first, and oldest first', () => {
    assert.equal(ids(sortCrises(list, { key: 'newest', dir: 'desc' })), 'c,d,a,b');
    assert.equal(ids(sortCrises(list, { key: 'newest', dir: 'asc' })), 'b,a,d,c');
  });

  it('country A to Z, ties most severe first, and Z to A', () => {
    assert.equal(ids(sortCrises(list, { key: 'country', dir: 'asc' })), 'd,b,c,a');
    assert.equal(ids(sortCrises(list, { key: 'country', dir: 'desc' })), 'c,a,b,d');
  });

  it('each key starts in its natural direction', () => {
    assert.equal(defaultDirection('severity'), 'desc');
    assert.equal(defaultDirection('newest'), 'desc');
    assert.equal(defaultDirection('country'), 'asc');
  });

  it('does not change the list it is given, and copes with empty and odd lists', () => {
    const copy = [...list];
    sortCrises(list, { key: 'country', dir: 'asc' });
    assert.deepEqual(list, copy);
    assert.deepEqual(sortCrises([], DEFAULT_CRISIS_SORT), []);
    const noDate = [crisis('x', 5, undefined as never, 'Peru'), crisis('y', 5, '2026-10-05T10:00:00', 'Peru')];
    assert.equal(sortCrises(noDate, { key: 'newest', dir: 'desc' }).length, 2);
  });
});

describe('short ages for dense rows', () => {
  const now = Date.parse('2026-10-06T12:00:00Z');
  const ago = (seconds: number) => new Date(now - seconds * 1000);

  it('now, minutes, hours, days', () => {
    assert.equal(shortAge(ago(0), now), 'now');
    assert.equal(shortAge(ago(59), now), 'now');
    assert.equal(shortAge(ago(60), now), '1m');
    assert.equal(shortAge(ago(59 * 60 + 59), now), '59m');
    assert.equal(shortAge(ago(3600), now), '1h');
    assert.equal(shortAge(ago(23 * 3600 + 3599), now), '23h');
    assert.equal(shortAge(ago(24 * 3600), now), '1d');
    assert.equal(shortAge(ago(99 * 86400), now), '99d');
    assert.equal(shortAge(ago(400 * 86400), now), '99d+');
  });

  it('a time in the future reads as now; nothing or garbage reads as empty', () => {
    assert.equal(shortAge(new Date(now + 3_600_000), now), 'now');
    assert.equal(shortAge(null, now), '');
    assert.equal(shortAge(new Date('nonsense'), now), '');
  });
});

describe('severity badge tone', () => {
  it('matches the five bands', () => {
    const cases: [number, string][] = [[0, 'sev1'], [19, 'sev1'], [20, 'sev2'], [39, 'sev2'], [40, 'sev3'], [59, 'sev3'], [60, 'sev4'], [79, 'sev4'], [80, 'sev5'], [100, 'sev5']];
    for (const [severity, tone] of cases) assert.equal(severityTone(severity), tone, String(severity));
  });

  it('stays in range for odd values', () => {
    assert.equal(severityTone(-5), 'sev1');
    assert.equal(severityTone(250), 'sev5');
  });
});
