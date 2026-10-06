import type { CrisisSummary, Storm } from '../api/types';
import type { EventsTab } from '../state/uiStore';

// The All / Major / Categories filter, applied identically to the left-hand
// list and to what the globe draws, in both Events and Weather mode. Keeping
// the rules here (not inside each component) is what keeps the two in sync.

// Events: "Major" is Severe or Critical on the five-level scale (60 or more).
export const MAJOR_SEVERITY = 60;

// `nightIds`, when given, keeps only those events (first reported at night, local time); null leaves the list as is.
export function applyCrisisFilter(
  list: CrisisSummary[],
  tab: EventsTab,
  category: string | null,
  nightIds: Set<string> | null = null,
): CrisisSummary[] {
  let result = list;
  if (tab === 'major') result = result.filter((c) => c.severity >= MAJOR_SEVERITY);
  else if (tab === 'categories' && category) result = result.filter((c) => c.type === category);
  if (nightIds) result = result.filter((c) => nightIds.has(c.id));
  return result;
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
