// Run with: npm test   (Node's built-in runner; Node 22.18+ runs the TypeScript directly.)
import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import { cleanClocks, cleanPrefs, loadClockPrefs, loadClocks, MAX_CLOCKS, saveClocks } from '../src/lib/clocks.ts';
import {
  cityName, formatOffset, isKnownZone, MODERN_NAMES, offsetMinutes, readClock, searchZones, supportedZones,
  zoneInfo, zonesLike, zoneSignature,
} from '../src/lib/timezones.ts';

const JAN = new Date('2026-01-15T12:00:00Z');
const JUL = new Date('2026-07-15T12:00:00Z');
const OCT = new Date('2026-10-06T12:00:00Z');

describe('offsets', () => {
  it('reads whole, half-hour and quarter-hour offsets', () => {
    assert.equal(offsetMinutes('UTC', OCT), 0);
    assert.equal(offsetMinutes('Asia/Tokyo', OCT), 540);
    assert.equal(offsetMinutes('Asia/Kolkata', OCT), 330);
    assert.equal(offsetMinutes('Asia/Kathmandu', OCT), 345);
    assert.equal(offsetMinutes('America/St_Johns', JAN), -210);
    assert.equal(offsetMinutes('Pacific/Chatham', JAN), 825);
  });

  it('follows daylight saving in both hemispheres', () => {
    assert.equal(offsetMinutes('America/New_York', JAN), -300);
    assert.equal(offsetMinutes('America/New_York', JUL), -240);
    assert.equal(offsetMinutes('Australia/Sydney', JAN), 660);
    assert.equal(offsetMinutes('Australia/Sydney', JUL), 600);
  });

  it('returns null for a zone the browser does not know', () => {
    assert.equal(offsetMinutes('Not/AZone', OCT), null);
  });

  it('formats offsets', () => {
    assert.equal(formatOffset(0), 'UTC');
    assert.equal(formatOffset(345), 'UTC+5:45');
    assert.equal(formatOffset(330), 'UTC+5:30');
    assert.equal(formatOffset(-180), 'UTC-3');
    assert.equal(formatOffset(-210), 'UTC-3:30');
    assert.equal(formatOffset(840), 'UTC+14');
    assert.equal(formatOffset(null), 'unknown offset');
  });
});

describe('daylight saving', () => {
  it('a zone without it', () => {
    const tokyo = zoneInfo('Asia/Tokyo', OCT);
    assert.equal(tokyo.pattern, 'none');
    assert.equal(tokyo.dstNow, false);
    assert.equal(tokyo.offsetLabel, 'UTC+9');
  });

  it('a northern zone: on in July, off in January', () => {
    assert.equal(zoneInfo('America/New_York', JUL).pattern, 'dst');
    assert.equal(zoneInfo('America/New_York', JUL).dstNow, true);
    assert.equal(zoneInfo('America/New_York', JAN).dstNow, false);
  });

  it('a southern zone: on in January, off in July', () => {
    assert.equal(zoneInfo('Australia/Sydney', JAN).dstNow, true);
    assert.equal(zoneInfo('Australia/Sydney', JUL).dstNow, false);
  });

  it('a few-week change is not called daylight saving', () => {
    assert.equal(zoneInfo('Africa/Casablanca', OCT).pattern, 'irregular');
    assert.equal(zoneInfo('Africa/Casablanca', OCT).dstNow, false);
  });
});

describe('zones with the same current rules', () => {
  it('matches zones that agree all year and not ones that differ', () => {
    const like = zonesLike('Europe/Paris', OCT);
    assert.ok(like.includes('Europe/Berlin'));
    assert.ok(!like.includes('Europe/London'));
    assert.ok(!like.includes('Europe/Paris'));
  });

  it('different daylight-saving behaviour with the same offset today is not the same zone', () => {
    // Phoenix and Denver share an offset in winter but not in summer.
    assert.notEqual(zoneSignature('America/Phoenix', OCT), zoneSignature('America/Denver', OCT));
  });
});

describe('clock readings', () => {
  const lateUtc = new Date('2026-10-06T23:30:00Z');

  it('reads time and the day against UTC', () => {
    assert.deepEqual(readClock('Asia/Tokyo', lateUtc), { time: '08:30', date: 'Wed, Oct 7', day: 'tomorrow' });
    assert.equal(readClock('Pacific/Honolulu', lateUtc)?.day, 'today');
    assert.equal(readClock('Pacific/Kiritimati', lateUtc)?.day, 'tomorrow');
    assert.equal(readClock('Pacific/Pago_Pago', new Date('2026-10-06T05:00:00Z'))?.day, 'yesterday');
    assert.equal(readClock('UTC', lateUtc)?.day, 'today');
  });

  it('honours the 12-hour and ISO choices', () => {
    const reading = readClock('Asia/Tokyo', lateUtc, { hour12: true, dateFormat: 'iso' });
    assert.equal(reading?.time, '08:30 AM');
    assert.equal(reading?.date, '2026-10-07');
  });

  it('gives null for an unknown zone', () => {
    assert.equal(readClock('Not/AZone', lateUtc), null);
  });
});

describe('zone names and search', () => {
  it('turns ids into city names', () => {
    assert.equal(cityName('America/Argentina/Buenos_Aires'), 'Buenos Aires');
    assert.equal(cityName('Asia/Kathmandu'), 'Kathmandu');
    assert.equal(cityName('UTC'), 'UTC');
  });

  it('knows real zones and refuses made-up or oversized ones', () => {
    assert.equal(isKnownZone('America/New_York'), true);
    assert.equal(isKnownZone('UTC'), true);
    assert.equal(isKnownZone('Not/AZone'), false);
    assert.equal(isKnownZone(5), false);
    assert.equal(isKnownZone('A'.repeat(100)), false);
    assert.equal(isKnownZone(''), false);
  });

  it('lists zones without legacy aliases and always includes UTC', () => {
    const zones = supportedZones();
    assert.ok(zones.length > 300);
    assert.ok(zones.includes('UTC') && zones.includes('Asia/Tokyo'));
    assert.ok(!zones.some((z) => z.startsWith('Etc/')));
  });

  it('lists current zone names, not the old ones some browsers still report', () => {
    const zones = supportedZones();
    for (const [old, modern] of Object.entries(MODERN_NAMES)) {
      assert.ok(!zones.includes(old), `${old} should have been renamed`);
      if (Intl.supportedValuesOf('timeZone').includes(old)) assert.ok(zones.includes(modern), `${modern} missing`);
    }
    assert.equal(searchZones('kolkata')[0], 'Asia/Kolkata');
    assert.equal(searchZones('kathmandu')[0], 'Asia/Kathmandu');
    assert.equal(new Set(zones).size, zones.length);
  });

  it('searches by city, best matches first, and ignores very short queries', () => {
    assert.equal(searchZones('new y')[0], 'America/New_York');
    assert.ok(searchZones('tokyo').includes('Asia/Tokyo'));
    assert.deepEqual(searchZones('a'), []);
    assert.deepEqual(searchZones('   '), []);
    assert.ok(searchZones('america').length <= 8);
    assert.deepEqual(searchZones('zzzzzz'), []);
  });
});

describe('saved clocks and options', () => {
  const real = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  afterEach(() => {
    if (real) Object.defineProperty(globalThis, 'localStorage', real);
    else delete (globalThis as Record<string, unknown>).localStorage;
  });

  it('cleans a list of anything invalid, duplicated or beyond the limit', () => {
    assert.deepEqual(cleanClocks(['Asia/Tokyo', 'Asia/Tokyo', 'Nope/Nope', 5, null, 'UTC']), ['Asia/Tokyo', 'UTC']);
    assert.deepEqual(cleanClocks('Asia/Tokyo'), []);
    assert.deepEqual(cleanClocks(undefined), []);
    const many = supportedZones().slice(0, 20);
    assert.equal(cleanClocks(many).length, MAX_CLOCKS);
  });

  it('cleans options to safe defaults', () => {
    assert.deepEqual(cleanPrefs({ hour12: true, dateFormat: 'iso' }), { hour12: true, dateFormat: 'iso' });
    assert.deepEqual(cleanPrefs({ hour12: 'yes', dateFormat: 'weird' }), { hour12: false, dateFormat: 'long' });
    assert.deepEqual(cleanPrefs(null), { hour12: false, dateFormat: 'long' });
  });

  it('survives storage that throws', () => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('blocked');
      },
    });
    assert.deepEqual(loadClocks(), []);
    assert.deepEqual(loadClockPrefs(), { hour12: false, dateFormat: 'long' });
    assert.doesNotThrow(() => saveClocks(['UTC']));
  });

  it('round-trips through storage and ignores corrupt data', () => {
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    });
    saveClocks(['Asia/Tokyo', 'UTC']);
    assert.deepEqual(loadClocks(), ['Asia/Tokyo', 'UTC']);
    store.set('geointel.clocks', '{not json');
    assert.deepEqual(loadClocks(), []);
  });
});
