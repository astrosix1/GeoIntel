// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { nightRing, subsolarPoint, sunAltitude, sunPosition, sunTimes, terminatorLine } from '../src/lib/sun.ts';

function near(actual: number, expected: number, tolerance: number, what: string) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${what}: expected ${expected} +/- ${tolerance}, got ${actual}`);
}

// Minutes between two instants.
function minutesApart(a: Date | null, iso: string): number {
  assert.ok(a, 'expected a time');
  return Math.abs(a.getTime() - new Date(iso).getTime()) / 60000;
}

function inRing(lon: number, lat: number, ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

describe('sun position', () => {
  it('declination at the solstices and equinoxes', () => {
    near(sunPosition(new Date('2026-06-21T12:00:00Z')).declination, 23.44, 0.1, 'June solstice');
    near(sunPosition(new Date('2026-12-21T12:00:00Z')).declination, -23.44, 0.1, 'December solstice');
    near(sunPosition(new Date('2026-03-20T15:00:00Z')).declination, 0, 0.1, 'March equinox');
    near(sunPosition(new Date('2026-09-23T01:00:00Z')).declination, 0, 0.1, 'September equinox');
  });

  it('equation of time is about +16 minutes in early November and about -14 in mid February', () => {
    near(sunPosition(new Date('2026-11-03T12:00:00Z')).equationOfTime, 16.4, 0.5, 'November');
    near(sunPosition(new Date('2026-02-11T12:00:00Z')).equationOfTime, -14.2, 0.5, 'February');
  });

  it('the sun is overhead at the equator on the equinox, near Greenwich at 12:00 UTC', () => {
    const p = subsolarPoint(new Date('2026-03-20T12:00:00Z'));
    near(p.lat, 0.2, 0.5, 'latitude');
    near(Math.abs(p.lon), 0, 5, 'longitude near Greenwich');
  });

  it('the subsolar point moves west 15 degrees an hour', () => {
    const a = subsolarPoint(new Date('2026-07-01T10:00:00Z'));
    const b = subsolarPoint(new Date('2026-07-01T11:00:00Z'));
    near(((a.lon - b.lon + 540) % 360) - 180, 15, 0.1, 'degrees per hour');
  });

  it('wraps across the date line', () => {
    const p = subsolarPoint(new Date('2026-07-01T00:00:00Z'));
    assert.ok(p.lon >= -180 && p.lon <= 180);
    near(Math.abs(p.lon), 180, 5, 'midnight UTC: sun near the date line');
  });
});

describe('sun altitude', () => {
  it('is high at local noon and negative at local midnight', () => {
    const noonLondon = new Date('2026-06-21T12:00:00Z');
    near(sunAltitude(51.5, -0.13, noonLondon), 61.9, 0.5, 'London solstice noon');
    assert.ok(sunAltitude(51.5, -0.13, new Date('2026-06-21T00:30:00Z')) < 0);
    assert.ok(sunAltitude(0, 180, new Date('2026-03-20T12:00:00Z')) < -80);
  });
});

// Reference times are from Open-Meteo's archive for the same places (dates in 2025, which differ from
// 2026 by well under a minute).
describe('sunrise, sunset and day length', () => {
  const cases: [string, number, number, string, string, string, string][] = [
    ['London, June solstice', 51.5074, -0.1278, '2026-06-21T12:00:00Z', '2026-06-21T03:43:00Z', '2026-06-21T20:21:00Z', '16:38'],
    ['Sydney, December solstice', -33.8688, 151.2093, '2026-12-21T02:00:00Z', '2026-12-20T18:40:00Z', '2026-12-21T09:05:00Z', '14:24'],
    ['Quito, March equinox', -0.18, -78.47, '2026-03-20T17:00:00Z', '2026-03-20T11:17:00Z', '2026-03-20T23:24:00Z', '12:07'],
    ['Honolulu, September equinox', 21.3, -157.86, '2026-09-23T22:00:00Z', '2026-09-23T16:20:00Z', '2026-09-24T04:26:00Z', '12:06'],
    ['Nairobi, early October', -1.29, 36.82, '2026-10-06T09:00:00Z', '2026-10-06T03:17:00Z', '2026-10-06T15:24:00Z', '12:07'],
  ];

  for (const [name, lat, lon, around, sunrise, sunset] of cases) {
    it(`${name}: within three minutes of the reference`, () => {
      const t = sunTimes(lat, lon, new Date(around));
      assert.equal(t.status, 'normal');
      assert.ok(minutesApart(t.sunrise, sunrise) <= 3, `sunrise off by ${minutesApart(t.sunrise, sunrise)} min`);
      assert.ok(minutesApart(t.sunset, sunset) <= 3, `sunset off by ${minutesApart(t.sunset, sunset)} min`);
    });
  }

  it('day length matches the reference durations', () => {
    near(sunTimes(51.5074, -0.1278, new Date('2026-06-21T12:00:00Z')).dayLengthHours, 59886.65 / 3600, 0.06, 'London');
    near(sunTimes(-33.8688, 151.2093, new Date('2026-12-21T02:00:00Z')).dayLengthHours, 51858.02 / 3600, 0.06, 'Sydney');
  });

  it('solar noon sits midway between sunrise and sunset', () => {
    const t = sunTimes(35.68, 139.69, new Date('2026-04-10T03:00:00Z'));
    assert.ok(t.sunrise && t.sunset);
    near((t.sunrise.getTime() + t.sunset.getTime()) / 2, t.solarNoon.getTime(), 1000, 'midpoint');
  });

  it('polar day and polar night are stated, not blank', () => {
    const summer = sunTimes(69.65, 18.96, new Date('2026-06-21T12:00:00Z'));
    assert.equal(summer.status, 'polar-day');
    assert.equal(summer.sunrise, null);
    assert.equal(summer.dayLengthHours, 24);
    const winter = sunTimes(69.65, 18.96, new Date('2026-12-21T12:00:00Z'));
    assert.equal(winter.status, 'polar-night');
    assert.equal(winter.dayLengthHours, 0);
  });

  it('the day follows the place, so a far-east evening is still that local day', () => {
    // 20:00 UTC on 20 Dec is already the morning of 21 Dec in Sydney.
    const t = sunTimes(-33.8688, 151.2093, new Date('2026-12-20T20:00:00Z'));
    assert.ok(minutesApart(t.sunrise, '2026-12-20T18:40:00Z') <= 3);
  });
});

describe('night polygon', () => {
  it('covers the dark side and not the lit side', () => {
    const noon = new Date('2026-03-20T12:00:00Z');   // equinox, sun over Greenwich
    const ring = nightRing(noon);
    assert.equal(inRing(175, 0, ring), true);        // just before midnight, beside the date line
    assert.equal(inRing(0, 0, ring), false);         // noon at Greenwich
    assert.equal(inRing(100, 10, ring), true);       // late evening in Asia
    assert.equal(inRing(-60, 10, ring), false);      // morning in South America
  });

  it('puts the dark pole inside the night side', () => {
    const july = nightRing(new Date('2026-07-01T12:00:00Z'));
    assert.equal(inRing(0, -89, july), true);        // southern winter: south pole dark
    assert.equal(inRing(0, 89, july), false);
    const january = nightRing(new Date('2026-01-01T12:00:00Z'));
    assert.equal(inRing(0, 89, january), true);
    assert.equal(inRing(0, -89, january), false);
  });

  it('agrees with the sun altitude on a grid, away from the terminator', () => {
    const when = new Date('2026-10-06T14:25:00Z');
    const ring = nightRing(when);
    let checked = 0;
    for (let lat = -80; lat <= 80; lat += 10) {
      for (let lon = -175; lon <= 175; lon += 10) {
        const alt = sunAltitude(lat, lon, when);
        if (Math.abs(alt) < 3) continue;
        checked++;
        assert.equal(inRing(lon, lat, ring), alt < 0, `${lat},${lon} altitude ${alt.toFixed(1)}`);
      }
    }
    assert.ok(checked > 400);
  });

  it('the terminator spans the globe, stays within the latitude limits and the ring is closed', () => {
    const line = terminatorLine(new Date('2026-12-21T12:00:00Z'));
    assert.equal(line[0][0], -180);
    assert.equal(line[line.length - 1][0], 180);
    assert.ok(line.every(([, lat]) => lat >= -90 && lat <= 90));
    const ring = nightRing(new Date('2026-12-21T12:00:00Z'));
    assert.deepEqual(ring[0], ring[ring.length - 1]);
  });

  it('survives the exact equinox moment', () => {
    const ring = nightRing(new Date('2026-09-23T00:05:00Z'));
    assert.ok(ring.every(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat)));
  });
});
