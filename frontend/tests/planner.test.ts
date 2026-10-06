// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  cleanWorkHours, formatLine, hourCategory, localParts, pairGapNotes, parseTimeInput, plannerRows, shortDate,
  windowSummary, worstCategory, zonedToUtc,
} from '../src/lib/planner.ts';

const WORK = { start: 9, end: 18 };
const iso = (d: Date | null) => d?.toISOString().slice(0, 16);

describe('hour categories', () => {
  it('working hours, early, late and night, with the edges', () => {
    const expected: Record<number, string> = {
      0: 'night', 5: 'night', 6: 'early', 8: 'early', 9: 'working', 17: 'working', 18: 'late', 21: 'late', 22: 'night', 23: 'night',
    };
    for (const [hour, category] of Object.entries(expected)) assert.equal(hourCategory(Number(hour), WORK), category, `hour ${hour}`);
  });

  it('follows custom working hours', () => {
    assert.equal(hourCategory(7, { start: 7, end: 15 }), 'working');
    assert.equal(hourCategory(15, { start: 7, end: 15 }), 'late');
    assert.equal(hourCategory(6, { start: 7, end: 15 }), 'early');
    assert.equal(hourCategory(23, { start: 10, end: 24 }), 'working');
  });

  it('cleans bad working hours back to the default', () => {
    assert.deepEqual(cleanWorkHours({ start: 8, end: 16 }), { start: 8, end: 16 });
    assert.deepEqual(cleanWorkHours({ start: 18, end: 9 }), { start: 9, end: 18 });
    assert.deepEqual(cleanWorkHours({ start: 'a', end: 30 }), { start: 9, end: 18 });
    assert.deepEqual(cleanWorkHours(null), { start: 9, end: 18 });
  });

  it('takes the worst of several', () => {
    assert.equal(worstCategory(['working', 'late', 'early']), 'late');
    assert.equal(worstCategory(['working', 'night']), 'night');
    assert.equal(worstCategory(['working']), 'working');
  });
});

describe('local time to an instant', () => {
  it('an ordinary time', () => {
    assert.equal(iso(zonedToUtc('Asia/Tokyo', 2026, 11, 5, 23, 0).instant), '2026-11-05T14:00');
    assert.equal(iso(zonedToUtc('Asia/Kathmandu', 2026, 11, 5, 12, 0).instant), '2026-11-05T06:15');
    assert.equal(iso(zonedToUtc('UTC', 2026, 11, 5, 12, 0).instant), '2026-11-05T12:00');
  });

  it('daylight saving on either side of a change', () => {
    assert.equal(iso(zonedToUtc('America/New_York', 2026, 11, 2, 9, 0).instant), '2026-11-02T14:00');   // EST
    assert.equal(iso(zonedToUtc('America/New_York', 2026, 10, 30, 9, 0).instant), '2026-10-30T13:00');  // EDT
  });

  it('a time skipped when clocks go forward has no instant', () => {
    const newYork = zonedToUtc('America/New_York', 2026, 3, 8, 2, 30);
    assert.equal(newYork.status, 'gap');
    assert.equal(newYork.instant, null);
    assert.equal(zonedToUtc('Australia/Sydney', 2026, 10, 4, 2, 30).status, 'gap');
    assert.equal(zonedToUtc('America/New_York', 2026, 3, 8, 3, 0).status, 'ok');
  });

  it('a time repeated when clocks go back is flagged and uses the first', () => {
    const repeated = zonedToUtc('America/New_York', 2026, 11, 1, 1, 30);
    assert.equal(repeated.status, 'ambiguous');
    assert.equal(iso(repeated.instant), '2026-11-01T05:30');   // the first, still on daylight time
    assert.equal(zonedToUtc('America/New_York', 2026, 11, 1, 0, 30).status, 'ok');
  });

  it('reads local parts back', () => {
    assert.deepEqual(localParts('Asia/Tokyo', new Date('2026-11-05T14:00:00Z')), { year: 2026, month: 11, day: 5, hour: 23, minute: 0 });
    assert.equal(localParts('UTC', new Date('2026-11-05T00:00:00Z')).hour, 0);
  });
});

describe('planner grid', () => {
  const zones = ['Europe/London', 'Asia/Tokyo', 'America/New_York'];

  it('has 24 rows with each place in its own time and the day marked', () => {
    const rows = plannerRows('Europe/London', 2026, 11, 3, zones, WORK);
    assert.equal(rows.length, 24);
    const ten = rows[10];
    assert.equal(ten.cells[0].time, '10:00');
    assert.equal(ten.cells[1].time, '19:00');
    assert.equal(ten.cells[2].time, '05:00');
    assert.deepEqual(ten.cells.map((c) => c.category), ['working', 'late', 'night']);
    const evening = rows[20];
    assert.equal(evening.cells[1].time, '05:00');
    assert.equal(evening.cells[1].dayOffset, 1);
    assert.equal(rows[2].cells[2].dayOffset, -1);
    assert.equal(rows[10].cells[0].dayOffset, 0);
  });

  it('a skipped hour in the reference zone has no cells', () => {
    const rows = plannerRows('America/New_York', 2026, 3, 8, ['America/New_York', 'UTC'], WORK);
    assert.equal(rows[2].instant, null);
    assert.deepEqual(rows[2].cells, []);
    assert.equal(rows[3].cells[1].time, '07:00');
  });

  it('summarises a meeting window with the worst hour it touches', () => {
    const start = zonedToUtc('Europe/London', 2026, 11, 3, 16, 0).instant as Date;
    const summary = windowSummary(start, 120, zones, WORK);
    assert.equal(summary[0].start, '16:00');
    assert.equal(summary[0].end, '18:00');
    assert.equal(summary[0].worst, 'working');
    assert.equal(summary[1].start, '01:00');
    assert.equal(summary[1].worst, 'night');
    assert.equal(summary[1].startDay, 'Wed 4 Nov');
    assert.equal(summary[2].start, '11:00');
  });
});

describe('copy text', () => {
  it('formats a line per place', () => {
    const instant = new Date('2026-11-05T14:00:00Z');
    assert.equal(formatLine('Asia/Tokyo', instant), 'Tokyo 23:00 Thu 5 Nov');
    assert.equal(formatLine('America/New_York', instant, true), 'New York 9:00 AM Thu 5 Nov');
    assert.equal(formatLine('Asia/Kathmandu', instant), 'Kathmandu 19:45 Thu 5 Nov');
    assert.equal(shortDate('Pacific/Kiritimati', new Date('2026-11-05T14:00:00Z')), 'Fri 6 Nov');
  });
});

describe('daylight-saving notes', () => {
  it('flags the weeks when the US and UK clocks are out of step', () => {
    const notes = pairGapNotes(['America/New_York', 'Europe/London'], new Date('2026-03-15T12:00:00Z'));
    assert.equal(notes.length, 1);
    assert.match(notes[0], /London is 4 h ahead of New York now, but 5 h ahead three weeks earlier/);
  });

  it('says nothing in the calm months', () => {
    assert.deepEqual(pairGapNotes(['America/New_York', 'Europe/London'], new Date('2026-07-01T12:00:00Z')), []);
    assert.deepEqual(pairGapNotes(['America/New_York', 'Asia/Tokyo'], new Date('2026-12-01T12:00:00Z')), []);
  });

  it('a zone that never changes has nothing to flag against another that never changes', () => {
    assert.deepEqual(pairGapNotes(['Asia/Tokyo', 'Asia/Kolkata'], new Date('2026-03-15T12:00:00Z')), []);
  });

  it('handles a single place', () => {
    assert.deepEqual(pairGapNotes(['Asia/Tokyo'], new Date('2026-03-15T12:00:00Z')), []);
  });
});

describe('converter', () => {
  const NOW = new Date('2026-11-02T10:00:00Z');
  const ok = (text: string, defaultZone = 'UTC') => {
    const r = parseTimeInput(text, NOW, defaultZone);
    assert.ok(r.ok, `expected "${text}" to parse, got ${r.ok ? '' : r.error}`);
    return r;
  };
  const fail = (text: string) => {
    const r = parseTimeInput(text, NOW);
    assert.equal(r.ok, false, `expected "${text}" to be refused`);
    return r.ok ? '' : r.error;
  };

  it('reads the documented forms', () => {
    assert.equal(iso(ok('14:00 UTC').instant), '2026-11-02T14:00');
    assert.equal(iso(ok('9am New York').instant), '2026-11-02T14:00');
    assert.equal(iso(ok('9 am new york').instant), '2026-11-02T14:00');
    assert.equal(iso(ok('2026-11-02 17:30 Tokyo').instant), '2026-11-02T08:30');
    assert.equal(iso(ok('17:30 Asia/Tokyo').instant), '2026-11-02T08:30');
    assert.equal(iso(ok('9:30 pm Kolkata').instant), '2026-11-02T16:00');
    assert.equal(iso(ok('noon London').instant), '2026-11-02T12:00');
    assert.equal(iso(ok('midnight Tokyo').instant), '2026-11-01T15:00');
    assert.equal(iso(ok('tomorrow 9am Tokyo').instant), '2026-11-03T00:00');
    assert.equal(iso(ok('yesterday 14:00 UTC').instant), '2026-11-01T14:00');
  });

  it('uses the chosen place when none is typed', () => {
    assert.equal(iso(ok('9am', 'Asia/Tokyo').instant), '2026-11-02T00:00');
    assert.equal(iso(ok('9am').instant), '2026-11-02T09:00');
  });

  it('reads UTC offsets', () => {
    assert.equal(iso(ok('14:00 UTC+2').instant), '2026-11-02T12:00');
    assert.equal(iso(ok('14:00 UTC-5:30').instant), '2026-11-02T19:30');
    assert.equal(iso(ok('14:00 gmt+0530').instant), '2026-11-02T08:30');
  });

  it('uses the right daylight-saving offset for the date typed', () => {
    assert.equal(iso(ok('2026-07-01 9am New York').instant), '2026-07-01T13:00');
    assert.equal(iso(ok('2026-12-01 9am New York').instant), '2026-12-01T14:00');
  });

  it('refuses abbreviations that mean different things in different places', () => {
    assert.match(fail('3pm CST'), /different things in different places/);
    assert.match(fail('9am IST'), /different things/);
    assert.match(fail('9am EST'), /Use a city/);
    assert.match(fail('9am bst'), /different things/);
  });

  it('refuses unknown or ambiguous places', () => {
    assert.match(fail('9am Atlantis'), /don't know a place called "Atlantis"/);
    assert.match(fail('9am San'), /could be/);
  });

  it('refuses impossible times and dates', () => {
    assert.match(fail('25:00 UTC'), /not a valid time/);
    assert.match(fail('13pm UTC'), /not a valid time/);
    assert.match(fail('9:75 UTC'), /not a valid minute/);
    assert.match(fail('2026-02-30 9am UTC'), /not a real date/);
    assert.match(fail('2026-13-01 9am UTC'), /not a valid date/);
    assert.match(fail('14:00 UTC+20'), /not a real offset/);
  });

  it('refuses text with no time and empty text', () => {
    assert.match(fail('hello'), /couldn't find a time/);
    assert.match(fail('New York'), /couldn't find a time/);
    assert.match(fail(''), /Type a time/);
    assert.match(fail('   '), /Type a time/);
  });

  it('a time skipped by a clock change is refused, a repeated one is flagged', () => {
    assert.match(fail('2026-03-08 2:30am New York'), /doesn't exist in New York/);
    const repeated = ok('2026-11-01 1:30am New York');
    assert.equal(repeated.ok && repeated.ambiguous, true);
    assert.equal(ok('2026-11-02 1:30am New York').ok && (ok('2026-11-02 1:30am New York') as { ambiguous: boolean }).ambiguous, false);
  });

  it('does not run away on odd input', () => {
    assert.equal(parseTimeInput('9am ' + 'x'.repeat(5000), NOW).ok, false);
    assert.equal(parseTimeInput('<script>alert(1)</script>', NOW).ok, false);
  });
});
