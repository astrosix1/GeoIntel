// Run with: npm test
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import { buildShareUrl, parseShareTarget } from '../src/lib/shareLink.ts';
import { interiorPoint, isUnusualOffset, labelFeatures, labelPoints, shortOffset, unusualOffsetNote } from '../src/lib/zoneLabels.ts';
import { pointInPolygonRings } from '../src/lib/zoneLookup.ts';

const square = (x: number, y: number, size = 10) => [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]];

describe('label points', () => {
  it('the centroid of a plain shape', () => {
    const [x, y] = interiorPoint([square(0, 0)])!;
    assert.ok(Math.abs(x - 5) < 0.01 && Math.abs(y - 5) < 0.01);
  });

  it('a crescent whose centroid is outside still gets an inside point', () => {
    const crescent = [[0, 0], [10, 0], [10, 2], [2, 2], [2, 8], [10, 8], [10, 10], [0, 10], [0, 0]];
    const point = interiorPoint([crescent])!;
    assert.ok(point, 'expected a point');
    assert.equal(pointInPolygonRings(point[0], point[1], [crescent]), true);
  });

  it('avoids a hole', () => {
    const point = interiorPoint([square(0, 0), square(4, 4, 2)])!;
    assert.equal(pointInPolygonRings(point[0], point[1], [square(0, 0), square(4, 4, 2)]), true);
  });

  it('one label per zone, in its biggest polygon, and bad shapes are skipped', () => {
    const points = labelPoints({
      features: [
        { properties: { tzid: 'A/Big' }, geometry: { type: 'MultiPolygon', coordinates: [[square(0, 0, 2)], [square(50, 0, 10)]] } },
        { properties: { tzid: 5 }, geometry: { type: 'Polygon', coordinates: [square(0, 0)] } },
        { properties: { tzid: 'B/Point' }, geometry: { type: 'Point', coordinates: [1, 1] } },
        { properties: { tzid: 'C/Empty' }, geometry: { type: 'Polygon', coordinates: [] } },
      ],
    });
    assert.equal(points.length, 1);
    assert.equal(points[0].tzid, 'A/Big');
    assert.ok(points[0].lon > 50, 'label belongs in the bigger polygon');
    assert.deepEqual(labelPoints({}), []);
  });

  it('the real file gives one inside point per zone and is quick', () => {
    const file = JSON.parse(readFileSync(new URL('../public/timezones.geojson', import.meta.url), 'utf8'));
    const start = performance.now();
    const points = labelPoints(file);
    const ms = performance.now() - start;
    assert.equal(points.length, new Set(points.map((p) => p.tzid)).size);
    assert.ok(points.length >= 60, `only ${points.length} zones labelled`);
    assert.ok(points.every((p) => Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180));
    assert.ok(ms < 2000, `labelling took ${Math.round(ms)} ms`);
  });
});

describe('unusual offsets', () => {
  it('flags half-hour, quarter-hour and date-line offsets only', () => {
    for (const minutes of [330, 345, 210, 525, 780, 840, -660, -720, 570]) assert.equal(isUnusualOffset(minutes), true, String(minutes));
    for (const minutes of [0, 60, 540, -300, -240, 720, -600, 600]) assert.equal(isUnusualOffset(minutes), false, String(minutes));
    assert.equal(isUnusualOffset(null), false);
  });

  it('explains them in a line', () => {
    assert.match(unusualOffsetNote(330)!, /UTC\+5:30 is a half-hour offset/);
    assert.match(unusualOffsetNote(345)!, /UTC\+5:45 is a quarter-hour offset/);
    assert.match(unusualOffsetNote(840)!, /UTC\+14 is beside the International Date Line.*first places/);
    assert.match(unusualOffsetNote(-720)!, /UTC-12 is beside the International Date Line.*last places/);
    assert.equal(unusualOffsetNote(540), null);
    assert.equal(unusualOffsetNote(null), null);
  });
});

describe('label text', () => {
  it('shortens offsets', () => {
    assert.equal(shortOffset(0), '0');
    assert.equal(shortOffset(540), '+9');
    assert.equal(shortOffset(345), '+5:45');
    assert.equal(shortOffset(-210), '-3:30');
    assert.equal(shortOffset(null), '?');
  });

  it('builds a time and offset for each point at the given moment', () => {
    const points = [
      { tzid: 'Asia/Tokyo', lon: 139, lat: 36, area: 10 },
      { tzid: 'Asia/Kathmandu', lon: 85, lat: 28, area: 5 },
      { tzid: 'Not/AZone', lon: 0, lat: 0, area: 1 },
    ];
    const { features } = labelFeatures(points, new Date('2026-10-06T14:25:00Z'));
    assert.equal(features.length, 2);
    assert.equal(features[0].properties.text, '23:25\n+9');
    assert.equal(features[0].properties.unusual, false);
    assert.equal(features[1].properties.text, '20:10\n+5:45');
    assert.equal(features[1].properties.unusual, true);
  });
});

describe('shareable Time Zone links', () => {
  const BASE = 'https://geointel.test/';

  it('round-trips a zone and a list of clocks', () => {
    const zoneUrl = buildShareUrl({ kind: 'zone', tzid: 'Asia/Tokyo' }, BASE);
    assert.equal(zoneUrl, 'https://geointel.test/?view=timezone&zone=Asia%2FTokyo');
    assert.deepEqual(parseShareTarget(new URL(zoneUrl).search), { kind: 'zone', tzid: 'Asia/Tokyo' });
    const clocksUrl = buildShareUrl({ kind: 'clocks', zones: ['Asia/Tokyo', 'Europe/London'], skipped: 0 }, BASE);
    assert.deepEqual(parseShareTarget(new URL(clocksUrl).search), { kind: 'clocks', zones: ['Asia/Tokyo', 'Europe/London'], skipped: 0 });
  });

  it('refuses an unrecognised zone with a message instead of opening anything', () => {
    const target = parseShareTarget('?view=timezone&zone=Mars%2FOlympus');
    assert.equal(target?.kind, 'invalid');
    assert.match((target as { message: string }).message, /Mars\/Olympus.*isn't recognised/);
  });

  it('drops unknown names from a clocks list and says how many', () => {
    const target = parseShareTarget('?view=timezone&clocks=Asia%2FTokyo,Nope%2FNope,Europe%2FLondon,Asia%2FTokyo');
    assert.deepEqual(target, { kind: 'clocks', zones: ['Asia/Tokyo', 'Europe/London'], skipped: 2 });
  });

  it('a clocks list of only bad names is invalid', () => {
    assert.equal(parseShareTarget('?view=timezone&clocks=a,b,c')?.kind, 'invalid');
  });

  it('limits a very long list', () => {
    const many = Array.from({ length: 60 }, () => 'UTC').join(',');
    const target = parseShareTarget(`?view=timezone&clocks=${many}`);
    assert.equal(target?.kind, 'clocks');
  });

  it('a Time Zone link with nothing in it opens nothing, and Weather links still work', () => {
    assert.equal(parseShareTarget('?view=timezone'), null);
    assert.equal(parseShareTarget('?view=other'), null);
    assert.deepEqual(parseShareTarget('?view=weather&hazard=TC-123'), { kind: 'hazard', eventType: 'TC', id: 123 });
  });

  it('does not let a zone value be anything but a known zone', () => {
    assert.equal(parseShareTarget('?view=timezone&zone=%3Cscript%3E')?.kind, 'invalid');
    assert.equal(parseShareTarget(`?view=timezone&zone=${'A'.repeat(500)}`)?.kind, 'invalid');
  });
});
