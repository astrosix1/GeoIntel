// Theme choice: Dark (the default), Light, or Match my system. The choice is remembered in this browser (best
// effort: storage can be blocked) and applied as data-theme on <html>, which the tokens key off. This file
// imports nothing so it can be unit-tested (frontend/tests/theme.test.ts).

export type ThemeChoice = 'dark' | 'light' | 'system';
export type AppliedTheme = 'dark' | 'light';

export const DEFAULT_THEME: ThemeChoice = 'dark';
const KEY = 'geointel.theme';

export function cleanTheme(value: unknown): ThemeChoice {
  return value === 'light' || value === 'system' || value === 'dark' ? value : DEFAULT_THEME;
}

export function resolveTheme(choice: ThemeChoice, systemPrefersLight: boolean): AppliedTheme {
  if (choice === 'system') return systemPrefersLight ? 'light' : 'dark';
  return choice;
}

export function loadTheme(): ThemeChoice {
  try {
    return cleanTheme(localStorage.getItem(KEY));
  } catch {
    return DEFAULT_THEME;
  }
}

export function saveTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}

function systemPrefersLight(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
}

// Puts the theme on the page now, and keeps "Match my system" following the system until another choice is made.
let stopWatching: (() => void) | null = null;

export function applyTheme(choice: ThemeChoice): AppliedTheme {
  stopWatching?.();
  stopWatching = null;
  const apply = () => {
    const applied = resolveTheme(choice, systemPrefersLight());
    document.documentElement.setAttribute('data-theme', applied);
    return applied;
  };
  const applied = apply();
  if (choice === 'system' && window.matchMedia) {
    const query = window.matchMedia('(prefers-color-scheme: light)');
    query.addEventListener('change', apply);
    stopWatching = () => query.removeEventListener('change', apply);
  }
  return applied;
}

export function initTheme(): void {
  applyTheme(loadTheme());
}
