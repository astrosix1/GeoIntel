// Time zone facts for Time Zone mode, all from the browser's own tz database (Intl), which
// carries the full daylight-saving rules. Nothing is typed in by hand and nothing is fetched.
// This file imports nothing so it can be unit-tested directly (frontend/tests/timezones.test.ts).

export type DstPattern = 'none' | 'dst' | 'irregular';

export interface ZoneInfo {
  tzid: string;
  city: string;
  offsetMinutes: number | null;
  offsetLabel: string;
  // 'dst': the offset changes for part of the year (daylight saving). 'irregular': it changes, but for
  // only a few weeks (a rule such as Morocco's Ramadan change), which is not called daylight saving here.
  pattern: DstPattern;
  dstNow: boolean;
}

export interface ClockPrefs {
  hour12: boolean;
  dateFormat: 'long' | 'iso';
}

export const DEFAULT_CLOCK_PREFS: ClockPrefs = { hour12: false, dateFormat: 'long' };

const FALLBACK_ZONES = [
  'UTC', 'Europe/London', 'Europe/Paris', 'Europe/Moscow', 'Africa/Cairo', 'Africa/Lagos', 'Africa/Johannesburg',
  'Asia/Dubai', 'Asia/Karachi', 'Asia/Kolkata', 'Asia/Kathmandu', 'Asia/Dhaka', 'Asia/Bangkok', 'Asia/Shanghai',
  'Asia/Tokyo', 'Australia/Sydney', 'Pacific/Auckland', 'Pacific/Honolulu', 'America/Anchorage',
  'America/Los_Angeles', 'America/Denver', 'America/Chicago', 'America/New_York', 'America/Sao_Paulo',
];

// Some browsers (Chrome among them) still list a zone under its old name, for example Asia/Calcutta, so a
// search for "Kolkata" would find nothing. Where the browser also understands the current name, that is used.
export const MODERN_NAMES: Record<string, string> = {
  'America/Buenos_Aires': 'America/Argentina/Buenos_Aires',
  'America/Catamarca': 'America/Argentina/Catamarca',
  'America/Cordoba': 'America/Argentina/Cordoba',
  'America/Jujuy': 'America/Argentina/Jujuy',
  'America/Mendoza': 'America/Argentina/Mendoza',
  'America/Godthab': 'America/Nuuk',
  'America/Indianapolis': 'America/Indiana/Indianapolis',
  'America/Louisville': 'America/Kentucky/Louisville',
  'Asia/Calcutta': 'Asia/Kolkata',
  'Asia/Katmandu': 'Asia/Kathmandu',
  'Asia/Rangoon': 'Asia/Yangon',
  'Asia/Saigon': 'Asia/Ho_Chi_Minh',
  'Atlantic/Faeroe': 'Atlantic/Faroe',
  'Europe/Kiev': 'Europe/Kyiv',
  'Pacific/Enderbury': 'Pacific/Kanton',
};

function understands(tzid: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tzid });
    return true;
  } catch {
    return false;
  }
}

let zoneCache: string[] | null = null;

// Every zone the browser knows, as "Region/City" ids plus UTC. Legacy and "Etc/" aliases are left out.
export function supportedZones(): string[] {
  if (zoneCache) return zoneCache;
  let zones: string[];
  try {
    const all = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone');
    zones = all && all.length ? all : FALLBACK_ZONES;
  } catch {
    zones = FALLBACK_ZONES;
  }
  const current = zones.map((z) => (MODERN_NAMES[z] && understands(MODERN_NAMES[z]) ? MODERN_NAMES[z] : z));
  zoneCache = Array.from(new Set(['UTC', ...current.filter((z) => z.includes('/') && !z.startsWith('Etc/'))])).sort();
  return zoneCache;
}

export function isKnownZone(tzid: unknown): tzid is string {
  if (typeof tzid !== 'string' || tzid.length > 64) return false;
  if (supportedZones().includes(tzid)) return true;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tzid });
    return true;
  } catch {
    return false;
  }
}

// "America/Argentina/Buenos_Aires" -> "Buenos Aires"; "UTC" -> "UTC".
export function cityName(tzid: string): string {
  const leaf = tzid.split('/').pop() ?? tzid;
  return leaf.replace(/_/g, ' ');
}

export function regionName(tzid: string): string {
  return tzid.includes('/') ? tzid.split('/')[0] : '';
}

// Building an Intl formatter is the slow part, so one per zone is kept.
const offsetFormatters = new Map<string, Intl.DateTimeFormat | null>();

function offsetFormatter(tzid: string): Intl.DateTimeFormat | null {
  if (!offsetFormatters.has(tzid)) {
    try {
      offsetFormatters.set(tzid, new Intl.DateTimeFormat('en-US', { timeZone: tzid, timeZoneName: 'longOffset' }));
    } catch {
      offsetFormatters.set(tzid, null);
    }
  }
  return offsetFormatters.get(tzid) ?? null;
}

// Offset from UTC in minutes at an instant, or null if the browser cannot say.
export function offsetMinutes(tzid: string, at: Date): number | null {
  const formatter = offsetFormatter(tzid);
  if (!formatter) return null;
  try {
    const name = formatter.formatToParts(at).find((p) => p.type === 'timeZoneName')?.value ?? '';
    if (name === 'GMT') return 0;
    const match = /^GMT([+\-−])(\d{1,2})(?::(\d{2}))?$/.exec(name);
    if (!match) return null;
    const sign = match[1] === '+' ? 1 : -1;
    return sign * (Number(match[2]) * 60 + Number(match[3] ?? 0));
  } catch {
    return null;
  }
}

// "UTC+5:45", "UTC-3", "UTC".
export function formatOffset(minutes: number | null): string {
  if (minutes === null) return 'unknown offset';
  if (minutes === 0) return 'UTC';
  const sign = minutes > 0 ? '+' : '-';
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `UTC${sign}${h}${m ? `:${String(m).padStart(2, '0')}` : ''}`;
}

// The offset sampled on the 1st and 15th of every month of the instant's year (24 samples at 12:00 UTC).
export function yearOffsets(tzid: string, at: Date): (number | null)[] {
  const year = at.getUTCFullYear();
  const samples: (number | null)[] = [];
  for (let month = 0; month < 12; month++) {
    for (const day of [1, 15]) samples.push(offsetMinutes(tzid, new Date(Date.UTC(year, month, day, 12))));
  }
  return samples;
}

function classify(samples: (number | null)[]): { pattern: DstPattern; low: number | null; high: number | null } {
  const numbers = samples.filter((s): s is number => s !== null);
  if (numbers.length === 0) return { pattern: 'none', low: null, high: null };
  const low = Math.min(...numbers);
  const high = Math.max(...numbers);
  if (low === high) return { pattern: 'none', low, high };
  const minority = Math.min(numbers.filter((n) => n === low).length, numbers.filter((n) => n === high).length);
  // A change that lasts only a few weeks is not daylight saving.
  return { pattern: minority <= 3 ? 'irregular' : 'dst', low, high };
}

export function zoneInfo(tzid: string, at: Date): ZoneInfo {
  const offset = offsetMinutes(tzid, at);
  const { pattern, high } = classify(yearOffsets(tzid, at));
  return {
    tzid,
    city: cityName(tzid),
    offsetMinutes: offset,
    offsetLabel: formatOffset(offset),
    pattern,
    dstNow: pattern === 'dst' && offset !== null && offset === high,
  };
}

// Two zones share their current rules when their offsets agree on all 24 sample dates.
const signatureCache = new Map<string, string>();

export function zoneSignature(tzid: string, at: Date): string {
  const key = `${at.getUTCFullYear()}|${tzid}`;
  let signature = signatureCache.get(key);
  if (signature === undefined) {
    signature = yearOffsets(tzid, at).join(',');
    signatureCache.set(key, signature);
  }
  return signature;
}

// Every known zone with the same current offsets all year as `tzid`, other than itself, by city name.
export function zonesLike(tzid: string, at: Date, zones: string[] = supportedZones()): string[] {
  const signature = zoneSignature(tzid, at);
  return zones.filter((z) => z !== tzid && zoneSignature(z, at) === signature);
}

export interface ClockReading {
  time: string;
  date: string;
  // The local calendar day compared with the UTC day at the same instant.
  day: 'yesterday' | 'today' | 'tomorrow';
}

function ymd(tzid: string, at: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: tzid, year: 'numeric', month: '2-digit', day: '2-digit' }).format(at);
}

export function readClock(tzid: string, at: Date, prefs: ClockPrefs = DEFAULT_CLOCK_PREFS): ClockReading | null {
  try {
    const time = new Intl.DateTimeFormat('en-US', {
      timeZone: tzid, hour: '2-digit', minute: '2-digit', hour12: prefs.hour12,
    }).format(at);
    const date = prefs.dateFormat === 'iso'
      ? ymd(tzid, at)
      : new Intl.DateTimeFormat('en-US', { timeZone: tzid, weekday: 'short', day: 'numeric', month: 'short' }).format(at);
    const local = ymd(tzid, at);
    const utc = ymd('UTC', at);
    return { time, date, day: local < utc ? 'yesterday' : local > utc ? 'tomorrow' : 'today' };
  } catch {
    return null;
  }
}

// Matches a typed search against zone ids and city names, best matches first.
export function searchZones(query: string, zones: string[] = supportedZones(), limit = 8): string[] {
  const q = query.trim().toLowerCase().replace(/\s+/g, '_');
  if (q.length < 2) return [];
  const starts: string[] = [];
  const contains: string[] = [];
  for (const zone of zones) {
    const id = zone.toLowerCase();
    const city = (zone.split('/').pop() ?? zone).toLowerCase();
    if (city.startsWith(q)) starts.push(zone);
    else if (id.includes(q)) contains.push(zone);
  }
  return [...starts, ...contains].slice(0, limit);
}
