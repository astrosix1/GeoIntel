// How precisely a pin's position is known, from the backend's
// `location_confidence` (the feed's own signal: country 55, state 70, city 85;
// 90+ is a specific place found in the article or reported by the source).
export type Precision = 'country' | 'region' | 'city' | 'place';

export function precisionOf(confidence: number | null | undefined): Precision | null {
  if (confidence == null) return null;
  if (confidence >= 90) return 'place';
  if (confidence >= 71) return 'city';
  if (confidence >= 56) return 'region';
  return 'country';
}

const LABEL: Record<Precision, string> = {
  country: 'country level',
  region: 'region level',
  city: 'city level',
  place: 'specific place',
};

// "Reported by 4 outlets" for a merged story; nothing for a single report.
export function sourcesTag(sources: number | undefined, stories?: number): string | null {
  const outlets = sources && sources > 1 ? `reported by ${sources} outlets` : null;
  if (stories && stories > 1) return outlets ? `${stories} stories, ${outlets}` : `${stories} stories`;
  return outlets ? outlets.charAt(0).toUpperCase() + outlets.slice(1) : null;
}

// Short tag for popups and list rows. Statements (talks, criticism, threats)
// have no physical site at all, so they are always approximate.
export function pinTag(confidence: number | null | undefined, statement: boolean | undefined): string | null {
  const precision = precisionOf(confidence);
  if (statement) return precision ? `Statement, location approximate (${LABEL[precision]})` : 'Statement, location approximate';
  if (!precision) return null;
  return precision === 'place' ? 'Specific place' : `Location approximate (${LABEL[precision]})`;
}
