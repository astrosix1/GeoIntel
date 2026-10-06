// Weather-mode hazard presentation, shared by the globe pins, the legend and
// the Analysis view so the three always agree.
export const HAZARD_TYPES = [
  { code: 'TC', label: 'Cyclones', icon: '🌀' },
  { code: 'FL', label: 'Floods', icon: '🌊' },
  { code: 'WF', label: 'Wildfires', icon: '🔥' },
  { code: 'DR', label: 'Droughts', icon: '☀️' },
] as const;

import type { IconName } from '../ui/Icon';

// The drawn icon for a hazard type (the map pins still use the emoji above until the map stage).
export function hazardIconName(code: string): IconName {
  return code === 'TC' ? 'cyclone' : code === 'FL' ? 'flood' : code === 'WF' ? 'fire' : code === 'DR' ? 'sun' : 'warning';
}

export function hazardIcon(code: string): string {
  return HAZARD_TYPES.find((t) => t.code === code)?.icon ?? '⚠️';
}

// GDACS's own Green/Orange/Red humanitarian-impact classification.
export const ALERT_COLORS: Record<string, string> = {
  Red: '#ff2d55',
  Orange: '#ff9500',
  Green: '#34c759',
  Unknown: '#0ac8ff',
};
