// When a zone's clocks last changed and next change, found by scanning the browser's own tz database
// (Intl) forward and back, so no table is kept by hand. Imports only lib files so it can be unit-tested.
import { localParts } from './planner.ts';
import { cityName, offsetMinutes } from './timezones.ts';

const MIN_MS = 60_000;
const DAY_MS = 86_400_000;
const SCAN_STEP_DAYS = 2;
// Far enough to see a yearly change from any date; a zone with none in this span has none worth showing.
export const SCAN_DAYS = 430;

export interface ClockChange {
  // The instant the new offset starts (rounded to the minute).
  instant: Date;
  fromOffset: number;
  toOffset: number;
  // 'forward': clocks jump ahead; 'back': they fall back.
  direction: 'forward' | 'back';
  // The local clock reading just before and just after the change, in that zone ("02:00" to "03:00").
  localBefore: string;
  localAfter: string;
  // Size of the jump in minutes (always positive).
  shiftMinutes: number;
}

export interface ClockChanges {
  previous: ClockChange | null;
  next: ClockChange | null;
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

// The clock reading an instant shows under a given offset, e.g. 07:00 UTC at -300 reads "02:00".
function clockUnder(instantMs: number, offsetMin: number): string {
  const d = new Date(instantMs + offsetMin * MIN_MS);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

// Narrow an interval where the offset differs at its ends down to the minute the change happens.
function bisect(tzid: string, lo: number, hi: number, offsetLo: number): number {
  while (hi - lo > MIN_MS) {
    const mid = lo + Math.max(MIN_MS, Math.floor((hi - lo) / 2 / MIN_MS) * MIN_MS);
    const o = offsetMinutes(tzid, new Date(mid));
    if (o === offsetLo) lo = mid;
    else hi = mid;
  }
  return hi;
}

function describe(instant: number, fromOffset: number, toOffset: number): ClockChange {
  return {
    instant: new Date(instant),
    fromOffset,
    toOffset,
    direction: toOffset > fromOffset ? 'forward' : 'back',
    localBefore: clockUnder(instant, fromOffset),
    localAfter: clockUnder(instant, toOffset),
    shiftMinutes: Math.abs(toOffset - fromOffset),
  };
}

function scan(tzid: string, from: Date, sign: 1 | -1): ClockChange | null {
  const start = Math.floor(from.getTime() / MIN_MS) * MIN_MS;
  const startOffset = offsetMinutes(tzid, new Date(start));
  if (startOffset === null) return null;
  let previous = start;
  for (let d = SCAN_STEP_DAYS; d <= SCAN_DAYS + SCAN_STEP_DAYS; d += SCAN_STEP_DAYS) {
    const t = start + sign * d * DAY_MS;
    const o = offsetMinutes(tzid, new Date(t));
    if (o === null) return null;
    if (o !== startOffset) {
      const [lo, hi] = sign === 1 ? [previous, t] : [t, previous];
      // Offset at the earlier end of the interval and at the later end.
      const earlyOffset = sign === 1 ? startOffset : o;
      const lateOffset = sign === 1 ? o : startOffset;
      const instant = bisect(tzid, lo, hi, earlyOffset);
      return describe(instant, earlyOffset, lateOffset);
    }
    previous = t;
  }
  return null;
}

// The last change before `at` and the next after it, or null for either when there is none in about 14 months.
export function clockChanges(tzid: string, at: Date): ClockChanges {
  return { previous: scan(tzid, at, -1), next: scan(tzid, at, 1) };
}

function shift(minutes: number): string {
  const h = minutes / 60;
  return Number.isInteger(h) ? `${h} h` : `${minutes} min`;
}

// "forward 1 h" / "back 1 h".
export function describeShift(change: ClockChange): string {
  return `${change.direction === 'forward' ? 'forward' : 'back'} ${shift(change.shiftMinutes)}`;
}

// "Sun 8 Mar, 02:00 to 03:00 (clocks forward 1 h)" in the zone's own calendar and clock.
export function describeChange(tzid: string, change: ClockChange): string {
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const p = localParts(tzid, new Date(change.instant.getTime() - MIN_MS));
  const weekday = WEEKDAYS[new Date(Date.UTC(p.year, p.month - 1, p.day)).getUTCDay()];
  return `${weekday} ${p.day} ${MONTHS[p.month - 1]} ${p.year}, ${change.localBefore} to ${change.localAfter} (clocks ${describeShift(change)})`;
}

// For the clocks list: one short line, or a plain statement when the zone does not change.
export function nextChangeLine(tzid: string, at: Date): string {
  const { next } = clockChanges(tzid, at);
  if (!next) return `${cityName(tzid)}: no clock change in the next 14 months`;
  const p = localParts(tzid, new Date(next.instant.getTime() - MIN_MS));
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `Clocks go ${describeShift(next)} on ${p.day} ${MONTHS[p.month - 1]}`;
}
