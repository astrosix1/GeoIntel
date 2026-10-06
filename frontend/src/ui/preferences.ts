// Interface preferences that are remembered in this browser (best effort: storage can be blocked, in which case a
// choice lasts for the visit). This file imports nothing so it can be unit-tested (frontend/tests/preferences.test.ts).
// The theme, units, time zone and clock choices keep their own loaders (ui/theme.ts, lib/units.ts, lib/clocks.ts).

export type PanelsMode = 'docked' | 'overlay';

export const DEFAULT_PANELS: PanelsMode = 'docked';
export const DEFAULT_STARFIELD = true;

const PANELS_KEY = 'geointel.panels';
const STARFIELD_KEY = 'geointel.starfield';

export function cleanPanels(value: unknown): PanelsMode {
  return value === 'overlay' || value === 'docked' ? value : DEFAULT_PANELS;
}

export function cleanFlag(value: unknown, fallback: boolean): boolean {
  if (value === true || value === 'true' || value === '1') return true;
  if (value === false || value === 'false' || value === '0') return false;
  return fallback;
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}

export function loadPanels(): PanelsMode {
  return cleanPanels(read(PANELS_KEY));
}

export function savePanels(mode: PanelsMode): void {
  write(PANELS_KEY, mode);
}

export function loadStarfield(): boolean {
  return cleanFlag(read(STARFIELD_KEY), DEFAULT_STARFIELD);
}

export function saveStarfield(on: boolean): void {
  write(STARFIELD_KEY, String(on));
}

// Panels sit beside the map only when the window is wide enough for two panels and a useful map.
export const DOCK_MIN_WIDTH = 900;
