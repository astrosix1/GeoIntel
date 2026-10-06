// Weather-mode hazard presentation, shared by the globe pins, the legend and
// the Analysis view so the three always agree.
export const HAZARD_TYPES = [
  { code: 'TC', label: 'Cyclones' },
  { code: 'FL', label: 'Floods' },
  { code: 'WF', label: 'Wildfires' },
  { code: 'DR', label: 'Droughts' },
] as const;

import type { IconName } from '../ui/Icon';
import type { BadgeTone } from '../ui/Display';

const ALERT_TONES: Record<string, BadgeTone> = { Red: 'alertRed', Orange: 'alertOrange', Green: 'alertGreen' };

// The badge colour for a GDACS alert level (anything else is neutral).
export function alertTone(level: string | null | undefined): BadgeTone {
  return (level && ALERT_TONES[level]) || 'neutral';
}

// The drawn icon for a hazard type .
export function hazardIconName(code: string): IconName {
  return code === 'TC' ? 'cyclone' : code === 'FL' ? 'flood' : code === 'WF' ? 'fire' : code === 'DR' ? 'sun' : 'warning';
}

// GDACS's own Green/Orange/Red humanitarian-impact classification.
export const ALERT_COLORS: Record<string, string> = {
  Red: '#ff2d55',
  Orange: '#ff9500',
  Green: '#34c759',
  Unknown: '#0ac8ff',
};
