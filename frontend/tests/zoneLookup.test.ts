// Run with: npm test
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import { hasReportTime, isNightHour, parseUtc, reportedLocalTime } from '../src/lib/eventTime.ts';
import { buildZoneIndex, zoneAt } from '../src/lib/zoneLookup.ts';
import { offsetMinutes } from '../src/lib/timezones.ts';

const square = (x: number, y: number, size = 10) => [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]];

describe('zone lookup (synthetic shapes)', () => {
  const index = buildZoneIndex({
    features: [
      { properties: { tzid: 'Zone/A' }, geometry: { type: 'Polygon', coordinates: [square(0, 0), square(4, 4, 2)] } },
      { properties: { tzid: 'Zone/B' }, geometry: { type: 'MultiPolygon', coordinates: [[square(20, 0)], [square(40, 0)]] } },
      { properties: { tzid: 42 }, geometry: { type: 'Polygon', coordinates: [square(60, 0)] } },
      { properties: { tzid: 'Zone/Broken' }, geometry: { type: 'Point', coordinates: [1, 1] } },
      { properties: { tzid: 'Zone/Empty' }, geometry: { type: 'Polygon', coordinates: [] } },
    ],
  });

  it('finds the polygon a point is in, including each part of a multipolygon', () => {
    assert.equal(zoneAt(index, 2, 2), 'Zone/A');
    assert.equal(zoneAt(index, 5, 25), 'Zone/B');
    assert.equal(zoneAt(index, 5, 45), 'Zone/B');
  });

  it('a hole is not inside', () => {
    assert.equal(zoneAt(index, 5, 5), null);
  });

  it('outside everything, and shapes it cannot use, give null', () => {
    assert.equal(zoneAt(index, 5, 100), null);
    assert.equal(zoneAt(index, 5, 65), null);
    assert.equal(zoneAt(index, 1, 1), 'Zone/A');
  });

  it('refuses impossible coordinates', () => {
    assert.equal(zoneAt(index, NaN, 2), null);
    assert.equal(zoneAt(index, 91, 2), null);
    assert.equal(zoneAt(index, 2, 181), null);
  });

  it('remembers answers', () => {
    zoneAt(index, 3, 3);
    assert.equal(index.cache.get('3,3'), 'Zone/A');
  });

  it('an empty or odd file gives an empty index', () => {
    assert.equal(buildZoneIndex({}).entries.length, 0);
    assert.equal(zoneAt(buildZoneIndex({ features: [] }), 0, 0), null);
  });
});

describe('zone lookup (the real boundary file)', () => {
  const file = JSON.parse(readFileSync(new URL('../public/timezones.geojson', import.meta.url), 'utf8'));
  const index = buildZoneIndex(file);
  const NOW = new Date('2026-10-06T12:00:00Z');
  const offsetAt = (lat: number, lon: number) => {
    const zone = zoneAt(index, lat, lon);
    assert.ok(zone, `no zone at ${lat},${lon}`);
    return offsetMinutes(zone, NOW);
  };

  it('puts well-known places in a zone with the right current offset', () => {
    assert.equal(offsetAt(51.5074, -0.1278), 60);      // London (BST in October)
    assert.equal(offsetAt(40.7128, -74.006), -240);    // New York
    assert.equal(offsetAt(35.6762, 139.6503), 540);    // Tokyo
    assert.equal(offsetAt(27.7172, 85.324), 345);      // Kathmandu
    assert.equal(offsetAt(6.5244, 3.3792), 60);        // Lagos
    assert.equal(offsetAt(-33.8688, 151.2093), 660);   // Sydney (clocks went forward on 4 October)
    assert.equal(offsetAt(28.6139, 77.209), 330);      // Delhi
    assert.equal(offsetAt(34.0522, -118.2437), -420);  // Los Angeles
  });

  it('open ocean has no zone', () => {
    assert.equal(zoneAt(index, 0, -30), null);
    assert.equal(zoneAt(index, -40, 100), null);
  });

  it('a few thousand lookups are quick', () => {
    const start = performance.now();
    for (let i = 0; i < 3000; i++) zoneAt(index, ((i * 7919) % 14000) / 100 - 30, ((i * 104729) % 33000) / 100 - 120);
    const ms = performance.now() - start;
    assert.ok(ms < 1500, `3000 lookups took ${Math.round(ms)} ms`);
  });
});

describe('when an event was first reported, locally', () => {
  it('reads UTC times that carry no zone suffix', () => {
    assert.equal(parseUtc('2026-10-05T15:45:00')?.toISOString(), '2026-10-05T15:45:00.000Z');
    assert.equal(parseUtc('2026-10-05T15:45:00Z')?.toISOString(), '2026-10-05T15:45:00.000Z');
    assert.equal(parseUtc('2026-10-05T15:45:00+02:00')?.toISOString(), '2026-10-05T13:45:00.000Z');
    assert.equal(parseUtc('not a date'), null);
    assert.equal(parseUtc(null), null);
    assert.equal(parseUtc(''), null);
  });

  it('night is 22:00 up to 05:00', () => {
    for (const [hour, night] of [[21, false], [22, true], [23, true], [0, true], [4, true], [5, false], [12, false]] as const) {
      assert.equal(isNightHour(hour), night, `hour ${hour}`);
    }
  });

  it('converts to the zone and flags night', () => {
    assert.deepEqual(reportedLocalTime('2026-10-05T15:45:00', 'Asia/Tokyo', 90), { time: '00:45', night: true, approximate: false });
    assert.deepEqual(reportedLocalTime('2026-10-05T15:45:00', 'America/New_York', 85), { time: '11:45', night: false, approximate: false });
  });

  it('marks a coarse pin as approximate and refuses bad input', () => {
    assert.equal(reportedLocalTime('2026-10-05T15:45:00', 'Asia/Tokyo', 70)?.approximate, true);
    assert.equal(reportedLocalTime('2026-10-05T15:45:00', 'Asia/Tokyo', null)?.approximate, true);
    assert.equal(reportedLocalTime('nope', 'Asia/Tokyo', 90), null);
    assert.equal(reportedLocalTime('2026-10-05T15:45:00', 'Not/AZone', 90), null);
  });

  it('only GDELT events have a time of day', () => {
    assert.equal(hasReportTime('gdelt_1325553434'), true);
    assert.equal(hasReportTime('acled_123'), false);
    assert.equal(hasReportTime('sample-1'), false);
  });
});
