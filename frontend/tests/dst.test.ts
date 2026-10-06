// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { clockChanges, describeChange, describeShift, nextChangeLine } from '../src/lib/dst.ts';

const OCT = new Date('2026-10-06T12:00:00Z');
const iso = (d: Date | undefined) => d?.toISOString().slice(0, 16);

describe('clock changes', () => {
  it('New York: last spring forward, next fall back, to the minute', () => {
    const { previous, next } = clockChanges('America/New_York', OCT);
    assert.equal(iso(previous?.instant), '2026-03-08T07:00');
    assert.equal(previous?.direction, 'forward');
    assert.equal(previous?.localBefore, '02:00');
    assert.equal(previous?.localAfter, '03:00');
    assert.equal(iso(next?.instant), '2026-11-01T06:00');
    assert.equal(next?.direction, 'back');
    assert.equal(next?.localBefore, '02:00');
    assert.equal(next?.localAfter, '01:00');
    assert.equal(next?.shiftMinutes, 60);
  });

  it('London', () => {
    const { previous, next } = clockChanges('Europe/London', OCT);
    assert.equal(iso(previous?.instant), '2026-03-29T01:00');
    assert.equal(previous?.localBefore, '01:00');
    assert.equal(previous?.localAfter, '02:00');
    assert.equal(iso(next?.instant), '2026-10-25T01:00');
    assert.equal(next?.direction, 'back');
  });

  it('Sydney, southern hemisphere: forward in October, back in April', () => {
    const { previous, next } = clockChanges('Australia/Sydney', OCT);
    assert.equal(iso(previous?.instant), '2026-10-03T16:00');
    assert.equal(previous?.direction, 'forward');
    assert.equal(iso(next?.instant), '2027-04-03T16:00');
    assert.equal(next?.direction, 'back');
  });

  it('a half-hour change', () => {
    const { previous } = clockChanges('Australia/Lord_Howe', OCT);
    assert.equal(previous?.shiftMinutes, 30);
    assert.equal(describeShift(previous!), 'forward 30 min');
  });

  it('zones that never change have none either side', () => {
    for (const zone of ['Asia/Tokyo', 'Asia/Kolkata', 'Asia/Kathmandu', 'UTC', 'Africa/Lagos']) {
      assert.deepEqual(clockChanges(zone, OCT), { previous: null, next: null }, zone);
    }
  });

  it('a few-week change (Morocco) is found in both directions', () => {
    const { previous, next } = clockChanges('Africa/Casablanca', OCT);
    assert.ok(previous && next);
    assert.equal(previous.direction, 'forward');
    assert.equal(next.direction, 'back');
  });

  it('results land on a whole minute even when asked at an odd moment', () => {
    const { next } = clockChanges('America/New_York', new Date('2026-10-06T12:00:37.123Z'));
    assert.equal(next?.instant.getUTCSeconds(), 0);
    assert.equal(next?.instant.getUTCMilliseconds(), 0);
    assert.equal(iso(next?.instant), '2026-11-01T06:00');
  });

  it('asking exactly at a change counts it as already happened', () => {
    const { previous, next } = clockChanges('America/New_York', new Date('2026-11-01T06:00:00Z'));
    assert.ok(previous && next);
    assert.equal(iso(next.instant) > '2026-11-01T06:00', true);
  });

  it('an unknown zone has none', () => {
    assert.deepEqual(clockChanges('Not/AZone', OCT), { previous: null, next: null });
  });
});

describe('wording', () => {
  it('describes a change in the zone\'s own calendar', () => {
    const { next } = clockChanges('America/New_York', OCT);
    assert.equal(describeChange('America/New_York', next!), 'Sun 1 Nov 2026, 02:00 to 01:00 (clocks back 1 h)');
    const { previous } = clockChanges('America/New_York', OCT);
    assert.equal(describeChange('America/New_York', previous!), 'Sun 8 Mar 2026, 02:00 to 03:00 (clocks forward 1 h)');
  });

  it('one-line summaries', () => {
    assert.equal(nextChangeLine('America/New_York', OCT), 'Clocks go back 1 h on 1 Nov');
    assert.equal(nextChangeLine('Asia/Tokyo', OCT), 'Tokyo: no clock change in the next 14 months');
  });
});
