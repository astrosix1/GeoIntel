// Meeting planner and time converter logic. Times come from the browser's tz database through lib/timezones.ts;
// nothing is guessed: an unreadable or ambiguous input is refused with a reason.
import { cityName, isKnownZone, offsetMinutes, supportedZones } from './timezones.ts';

const MIN_MS = 60_000;
const DAY_MS = 86_400_000;

// ---- working hours -------------------------------------------------------------------------------------------

export interface WorkHours {
  start: number;   // first working hour, 0-23
  end: number;     // first hour after work, 1-24
}

export const DEFAULT_WORK_HOURS: WorkHours = { start: 9, end: 18 };

export type HourCategory = 'working' | 'early' | 'late' | 'night';

const EARLY_FROM = 6;
const LATE_UNTIL = 22;

// Working hours are [start, end); the three hours before are "early" (not before 06:00), the hours after
// until 22:00 are "late"; everything else is night.
export function hourCategory(hour: number, work: WorkHours = DEFAULT_WORK_HOURS): HourCategory {
  if (hour >= work.start && hour < work.end) return 'working';
  if (hour >= Math.min(EARLY_FROM, work.start) && hour < work.start) return 'early';
  if (hour >= work.end && hour < Math.max(LATE_UNTIL, work.end)) return 'late';
  return 'night';
}

export function cleanWorkHours(value: unknown): WorkHours {
  const v = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>;
  const start = Number.isInteger(v.start) ? (v.start as number) : DEFAULT_WORK_HOURS.start;
  const end = Number.isInteger(v.end) ? (v.end as number) : DEFAULT_WORK_HOURS.end;
  if (start < 0 || start > 23 || end < 1 || end > 24 || end <= start) return { ...DEFAULT_WORK_HOURS };
  return { start, end };
}

const SEVERITY: Record<HourCategory, number> = { working: 0, early: 1, late: 2, night: 3 };

export function worstCategory(categories: HourCategory[]): HourCategory {
  return categories.reduce((worst, c) => (SEVERITY[c] > SEVERITY[worst] ? c : worst), 'working' as HourCategory);
}

// ---- local time <-> instant ----------------------------------------------------------------------------------------

export interface LocalParts {
  year: number;
  month: number;   // 1-12
  day: number;
  hour: number;
  minute: number;
}

const partsFormatters = new Map<string, Intl.DateTimeFormat>();

export function localParts(tzid: string, at: Date): LocalParts {
  let formatter = partsFormatters.get(tzid);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tzid, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', hourCycle: 'h23',
    });
    partsFormatters.set(tzid, formatter);
  }
  const get = (type: string) => Number(formatter.formatToParts(at).find((p) => p.type === type)?.value);
  return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour') % 24, minute: get('minute') };
}

export interface ZonedResult {
  status: 'ok' | 'gap' | 'ambiguous';
  // For 'ambiguous' (clocks go back, so the time happens twice) this is the first occurrence.
  instant: Date | null;
}

// The instant at which a zone's clocks read the given local date and time. A time skipped when clocks go
// forward has no instant ('gap'); a time repeated when clocks go back has two ('ambiguous').
export function zonedToUtc(tzid: string, year: number, month: number, day: number, hour: number, minute: number): ZonedResult {
  const localAsUtc = Date.UTC(year, month - 1, day, hour, minute);
  const offsets = new Set<number>();
  for (const shift of [-DAY_MS, 0, DAY_MS]) {
    const o = offsetMinutes(tzid, new Date(localAsUtc + shift));
    if (o !== null) offsets.add(o);
  }
  const valid: number[] = [];
  for (const o of offsets) {
    const t = localAsUtc - o * MIN_MS;
    if (offsetMinutes(tzid, new Date(t)) === o) valid.push(t);
  }
  valid.sort((a, b) => a - b);
  if (valid.length === 0) return { status: 'gap', instant: null };
  return { status: valid.length > 1 ? 'ambiguous' : 'ok', instant: new Date(valid[0]) };
}

// ---- planner grid --------------------------------------------------------------------------------------------------------

export interface PlannerCell {
  tzid: string;
  time: string;                 // "14:00"
  dayOffset: -1 | 0 | 1;        // the cell's date against the reference zone's date
  category: HourCategory;
}

export interface PlannerRow {
  hour: number;                 // the hour in the reference zone, 0-23
  instant: Date | null;         // null when the reference zone skips this hour
  cells: PlannerCell[];
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function dayNumber(p: LocalParts): number {
  return Math.floor(Date.UTC(p.year, p.month - 1, p.day) / DAY_MS);
}

// One row per hour of the reference zone's day, one cell per place with that place's own local time.
export function plannerRows(refZone: string, year: number, month: number, day: number, zones: string[], work: WorkHours): PlannerRow[] {
  const rows: PlannerRow[] = [];
  for (let hour = 0; hour < 24; hour++) {
    const { instant } = zonedToUtc(refZone, year, month, day, hour, 0);
    if (!instant) {
      rows.push({ hour, instant: null, cells: [] });
      continue;
    }
    const refDay = dayNumber(localParts(refZone, instant));
    const cells = zones.map((tzid) => {
      const p = localParts(tzid, instant);
      const diff = dayNumber(p) - refDay;
      return {
        tzid,
        time: `${pad(p.hour)}:${pad(p.minute)}`,
        dayOffset: (diff < 0 ? -1 : diff > 0 ? 1 : 0) as -1 | 0 | 1,
        category: hourCategory(p.hour, work),
      };
    });
    rows.push({ hour, instant, cells });
  }
  return rows;
}

export interface WindowPlace {
  tzid: string;
  start: string;
  end: string;
  startDay: string;
  worst: HourCategory;
}

// A meeting window of `minutes` starting at `start`: each place's local start and end and the worst
// kind of hour the window touches there (checked every half hour).
export function windowSummary(start: Date, minutes: number, zones: string[], work: WorkHours): WindowPlace[] {
  const end = new Date(start.getTime() + minutes * MIN_MS);
  return zones.map((tzid) => {
    const categories: HourCategory[] = [];
    for (let t = start.getTime(); t < end.getTime(); t += 30 * MIN_MS) categories.push(hourCategory(localParts(tzid, new Date(t)).hour, work));
    const s = localParts(tzid, start);
    const e = localParts(tzid, end);
    return {
      tzid,
      start: `${pad(s.hour)}:${pad(s.minute)}`,
      end: `${pad(e.hour)}:${pad(e.minute)}`,
      startDay: shortDate(tzid, start),
      worst: worstCategory(categories),
    };
  });
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// "Tue 5 Nov" in the zone's own calendar.
export function shortDate(tzid: string, at: Date): string {
  const p = localParts(tzid, at);
  const weekday = WEEKDAYS[new Date(Date.UTC(p.year, p.month - 1, p.day)).getUTCDay()];
  return `${weekday} ${p.day} ${MONTHS[p.month - 1]}`;
}

// One line per place for pasting into an email: "Tokyo 23:00 Tue 5 Nov".
export function formatLine(tzid: string, at: Date, hour12 = false): string {
  const p = localParts(tzid, at);
  const time = hour12
    ? `${p.hour % 12 === 0 ? 12 : p.hour % 12}:${pad(p.minute)} ${p.hour < 12 ? 'AM' : 'PM'}`
    : `${pad(p.hour)}:${pad(p.minute)}`;
  return `${cityName(tzid)} ${time} ${shortDate(tzid, at)}`;
}

// ---- daylight-saving notes ---------------------------------------------------------------------------------------------------

function hours(minutes: number): string {
  const h = minutes / 60;
  return Number.isInteger(h) ? `${h} h` : `${h.toFixed(2).replace(/0$/, '')} h`;
}

// Where the gap between two places is only temporary: when it differs three weeks before or after the chosen
// moment, one of them is changing its clocks nearby. Says so, once per pair.
export function pairGapNotes(zones: string[], at: Date): string[] {
  const notes: string[] = [];
  const WINDOW = 21 * DAY_MS;
  for (let i = 0; i < zones.length; i++) {
    for (let j = i + 1; j < zones.length; j++) {
      const gap = (t: Date) => {
        const a = offsetMinutes(zones[i], t);
        const b = offsetMinutes(zones[j], t);
        return a === null || b === null ? null : b - a;
      };
      const now = gap(at);
      const before = gap(new Date(at.getTime() - WINDOW));
      const after = gap(new Date(at.getTime() + WINDOW));
      if (now === null) continue;
      const other = before !== null && before !== now ? { value: before, when: 'three weeks earlier' } :
        after !== null && after !== now ? { value: after, when: 'three weeks later' } : null;
      if (other) {
        notes.push(
          `Clocks change near this date: ${cityName(zones[j])} is ${hours(Math.abs(now))} ${now >= 0 ? 'ahead of' : 'behind'} ${cityName(zones[i])} now, ` +
          `but ${hours(Math.abs(other.value))} ${other.value >= 0 ? 'ahead' : 'behind'} ${other.when}.`,
        );
      }
    }
  }
  return notes;
}

// ---- converter -----------------------------------------------------------------------------------------------------------------------

export type ParseResult =
  | { ok: true; instant: Date; label: string; zone: string | null; offsetMinutes: number; ambiguous: boolean }
  | { ok: false; error: string };

// Abbreviations that mean different things in different places (or that people use loosely).
const AMBIGUOUS_ABBREVIATIONS = new Set([
  'est', 'edt', 'cst', 'cdt', 'mst', 'mdt', 'pst', 'pdt', 'akst', 'akdt', 'hst', 'ast', 'adt', 'nst', 'ndt',
  'ist', 'bst', 'cet', 'cest', 'eet', 'eest', 'wet', 'west', 'msk', 'sast', 'wat', 'cat', 'eat', 'pkt', 'jst', 'kst',
  'aest', 'aedt', 'acst', 'acdt', 'awst', 'nzst', 'nzdt', 'sgt', 'hkt', 'pht',
]);

const FORMS = 'Try "14:00 UTC", "9am New York", "2026-11-02 17:30 Tokyo" or "tomorrow 9am London".';

function resolveZone(text: string, zones: string[]): { zone: string } | { error: string } {
  const q = text.trim().replace(/\s+/g, '_');
  if (zones.includes(text.trim())) return { zone: text.trim() };
  if (text.includes('/') && isKnownZone(text.trim())) return { zone: text.trim() };
  const lower = q.toLowerCase();
  const leaf = (z: string) => (z.split('/').pop() ?? z).toLowerCase();
  const exact = zones.filter((z) => leaf(z) === lower);
  if (exact.length === 1) return { zone: exact[0] };
  if (exact.length > 1) return { error: `More than one place is called "${text.trim()}" (${exact.slice(0, 4).join(', ')}). Use the full name.` };
  const starts = zones.filter((z) => leaf(z).startsWith(lower));
  if (starts.length === 1) return { zone: starts[0] };
  if (starts.length > 1) return { error: `"${text.trim()}" could be ${starts.slice(0, 4).map(cityName).join(', ')}${starts.length > 4 ? ' or more' : ''}. Be more specific.` };
  return { error: `I don't know a place called "${text.trim()}".` };
}

// Reads text such as "9am New York" into an instant. Only a small, documented set of forms is accepted; anything
// else is refused with a reason instead of being guessed.
export function parseTimeInput(text: string, now: Date = new Date(), defaultZone = 'UTC', zones: string[] = supportedZones()): ParseResult {
  let rest = ` ${text.trim().toLowerCase()} `;
  if (rest.trim() === '') return { ok: false, error: `Type a time. ${FORMS}` };

  // 1. date
  let dateWord: 'today' | 'tomorrow' | 'yesterday' | null = null;
  let isoDate: [number, number, number] | null = null;
  const iso = /\s(\d{4})-(\d{2})-(\d{2})(?=\s|$)/.exec(rest);
  if (iso) {
    isoDate = [Number(iso[1]), Number(iso[2]), Number(iso[3])];
    rest = rest.replace(iso[0], ' ');
  } else {
    const word = /\s(today|tomorrow|yesterday)(?=\s|$)/.exec(rest);
    if (word) {
      dateWord = word[1] as 'today' | 'tomorrow' | 'yesterday';
      rest = rest.replace(word[0], ' ');
    }
  }

  // 2. time
  let hour: number;
  let minute = 0;
  const named = /\s(noon|midnight)(?=\s|$)/.exec(rest);
  if (named) {
    hour = named[1] === 'noon' ? 12 : 0;
    rest = rest.replace(named[0], ' ');
  } else {
    const t = /\s(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?=\s|$)/.exec(rest);
    if (!t) return { ok: false, error: `I couldn't find a time in that. ${FORMS}` };
    hour = Number(t[1]);
    minute = t[2] ? Number(t[2]) : 0;
    if (minute > 59) return { ok: false, error: `${t[2]} is not a valid minute.` };
    if (t[3]) {
      if (hour < 1 || hour > 12) return { ok: false, error: `${hour}${t[3]} is not a valid time.` };
      hour = (hour % 12) + (t[3] === 'pm' ? 12 : 0);
    } else if (hour > 23) {
      return { ok: false, error: `${hour}:${String(minute).padStart(2, '0')} is not a valid time.` };
    }
    rest = rest.replace(t[0], ' ');
  }
  if (isoDate && (isoDate[1] < 1 || isoDate[1] > 12 || isoDate[2] < 1 || isoDate[2] > 31)) {
    return { ok: false, error: `${isoDate.join('-')} is not a valid date.` };
  }

  // 3. place
  const zoneText = rest.trim().replace(/\s+/g, ' ');
  let zone: string | null = null;
  let fixedOffset: number | null = null;
  if (zoneText === '') {
    zone = defaultZone;
  } else if (/^(utc|gmt|z)$/.test(zoneText)) {
    fixedOffset = 0;
  } else {
    const off = /^(?:utc|gmt)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$/.exec(zoneText);
    if (off) {
      const minutes = Number(off[2]) * 60 + Number(off[3] ?? 0);
      if (Number(off[2]) > 14 || (off[3] !== undefined && Number(off[3]) > 59)) return { ok: false, error: `${zoneText.toUpperCase()} is not a real offset.` };
      fixedOffset = (off[1] === '+' ? 1 : -1) * minutes;
    } else if (AMBIGUOUS_ABBREVIATIONS.has(zoneText)) {
      return { ok: false, error: `"${zoneText.toUpperCase()}" means different things in different places. Use a city (for example Chicago) or UTC+offset.` };
    } else {
      const found = resolveZone(originalZoneText(text, zoneText), zones);
      if ('error' in found) return { ok: false, error: found.error };
      zone = found.zone;
    }
  }

  // 4. instant
  const reference = new Date(now.getTime());
  const todayParts = zone ? localParts(zone, reference) : localParts('UTC', new Date(reference.getTime() + (fixedOffset ?? 0) * MIN_MS));
  let y = todayParts.year;
  let m = todayParts.month;
  let d = todayParts.day;
  if (isoDate) [y, m, d] = isoDate;
  else if (dateWord) {
    const shifted = new Date(Date.UTC(y, m - 1, d) + (dateWord === 'tomorrow' ? DAY_MS : dateWord === 'yesterday' ? -DAY_MS : 0));
    y = shifted.getUTCFullYear();
    m = shifted.getUTCMonth() + 1;
    d = shifted.getUTCDate();
  }
  const check = new Date(Date.UTC(y, m - 1, d));
  if (check.getUTCMonth() !== m - 1 || check.getUTCDate() !== d) return { ok: false, error: `${y}-${pad(m)}-${pad(d)} is not a real date.` };

  if (zone) {
    const r = zonedToUtc(zone, y, m, d, hour, minute);
    if (r.status === 'gap' || !r.instant) {
      return { ok: false, error: `${pad(hour)}:${pad(minute)} on ${y}-${pad(m)}-${pad(d)} doesn't exist in ${cityName(zone)}: clocks go forward and skip it.` };
    }
    return { ok: true, instant: r.instant, label: `${pad(hour)}:${pad(minute)} ${cityName(zone)}`, zone, offsetMinutes: offsetMinutes(zone, r.instant) ?? 0, ambiguous: r.status === 'ambiguous' };
  }
  const offset = fixedOffset ?? 0;
  const instant = new Date(Date.UTC(y, m - 1, d, hour, minute) - offset * MIN_MS);
  const sign = offset >= 0 ? '+' : '-';
  const label = offset === 0 ? `${pad(hour)}:${pad(minute)} UTC` : `${pad(hour)}:${pad(minute)} UTC${sign}${Math.floor(Math.abs(offset) / 60)}${Math.abs(offset) % 60 ? ':' + pad(Math.abs(offset) % 60) : ''}`;
  return { ok: true, instant, label, zone: null, offsetMinutes: offset, ambiguous: false };
}

// The zone words as typed (original case and spelling) so an exact IANA id such as "Asia/Tokyo" still matches.
function originalZoneText(original: string, lowerZoneText: string): string {
  const index = original.toLowerCase().lastIndexOf(lowerZoneText);
  return index >= 0 ? original.slice(index, index + lowerZoneText.length) : lowerZoneText;
}
