// What the user chose in Time Zone mode: the pinned clocks and the clock display options. Kept in
// this browser only (best effort: storage can be blocked, in which case choices last for the visit).
import { cleanWorkHours, DEFAULT_WORK_HOURS } from './planner.ts';
import type { WorkHours } from './planner.ts';
import { DEFAULT_CLOCK_PREFS, isKnownZone } from './timezones.ts';
import type { ClockPrefs } from './timezones.ts';

export const MAX_CLOCKS = 8;
const CLOCKS_KEY = 'geointel.clocks';
const PREFS_KEY = 'geointel.clockPrefs';
const WORK_KEY = 'geointel.workHours';

// A saved or shared list cleaned of anything that is not a real zone, duplicates and extras.
export function cleanClocks(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    if (isKnownZone(item) && !out.includes(item)) out.push(item);
    if (out.length === MAX_CLOCKS) break;
  }
  return out;
}

export function loadClocks(): string[] {
  try {
    return cleanClocks(JSON.parse(localStorage.getItem(CLOCKS_KEY) ?? '[]'));
  } catch {
    return [];
  }
}

export function saveClocks(clocks: string[]): void {
  try {
    localStorage.setItem(CLOCKS_KEY, JSON.stringify(clocks));
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}

export function cleanPrefs(value: unknown): ClockPrefs {
  const v = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>;
  return {
    hour12: typeof v.hour12 === 'boolean' ? v.hour12 : DEFAULT_CLOCK_PREFS.hour12,
    dateFormat: v.dateFormat === 'iso' ? 'iso' : 'long',
  };
}

export function loadClockPrefs(): ClockPrefs {
  try {
    return cleanPrefs(JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}'));
  } catch {
    return { ...DEFAULT_CLOCK_PREFS };
  }
}

export function saveClockPrefs(prefs: ClockPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}

export function loadWorkHours(): WorkHours {
  try {
    return cleanWorkHours(JSON.parse(localStorage.getItem(WORK_KEY) ?? 'null'));
  } catch {
    return { ...DEFAULT_WORK_HOURS };
  }
}

export function saveWorkHours(hours: WorkHours): void {
  try {
    localStorage.setItem(WORK_KEY, JSON.stringify(hours));
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}
