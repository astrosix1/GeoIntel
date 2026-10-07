// What the drawing tool shows when it measures, remembered in this browser (best effort: storage can be blocked, in which
// case a choice lasts for the visit). This file imports nothing so it can be unit-tested (frontend/tests/drawprefs.test.ts).

export type DrawUnits = 'auto' | 'metric' | 'imperial' | 'nautical';

export interface DrawPrefs {
  // "auto" follows the Units setting (metric or imperial); nautical is only ever chosen here.
  units: DrawUnits;
  segments: boolean; // the length of every segment of a line or polygon
  angles: boolean; // the angle at every corner
  bearings: boolean; // the compass bearing of every segment
}

export const DEFAULT_DRAW_PREFS: DrawPrefs = { units: 'auto', segments: false, angles: false, bearings: false };

const KEY = 'geointel.draw';
const UNITS: DrawUnits[] = ['auto', 'metric', 'imperial', 'nautical'];

// Anything that is not a recognised value falls back to the default for that field.
export function cleanDrawPrefs(value: unknown): DrawPrefs {
  const input = typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
  return {
    units: UNITS.includes(input.units as DrawUnits) ? (input.units as DrawUnits) : DEFAULT_DRAW_PREFS.units,
    segments: input.segments === true,
    angles: input.angles === true,
    bearings: input.bearings === true,
  };
}

export function loadDrawPrefs(): DrawPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    return cleanDrawPrefs(raw ? JSON.parse(raw) : null);
  } catch {
    return { ...DEFAULT_DRAW_PREFS };
  }
}

export function saveDrawPrefs(prefs: DrawPrefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}
