import type { CrisisSummary, Storm } from '../api/types';
import type { EventsTab } from '../state/uiStore';

// The All / Major / Categories filter, applied identically to the left-hand
// list and to what the globe draws, in both Events and Weather mode. Keeping
// the rules here (not inside each component) is what keeps the two in sync.

// Events: "Major" is a GDELT severity of 70 or more.
export const MAJOR_SEVERITY = 70;

export function applyCrisisFilter(list: CrisisSummary[], tab: EventsTab, category: string | null): CrisisSummary[] {
  if (tab === 'major') return list.filter((c) => c.severity >= MAJOR_SEVERITY);
  if (tab === 'categories' && category) return list.filter((c) => c.type === category);
  return list;
}

// Weather: "Major" is a GDACS Orange or Red alert; the categories are the
// hazard types (cyclone, flood, wildfire, drought).
export function isMajorHazard(hazard: Storm): boolean {
  return hazard.alert_level === 'Orange' || hazard.alert_level === 'Red';
}

export function applyHazardFilter(list: Storm[], tab: EventsTab, category: string | null): Storm[] {
  if (tab === 'major') return list.filter(isMajorHazard);
  if (tab === 'categories' && category) return list.filter((h) => h.event_type === category);
  return list;
}
