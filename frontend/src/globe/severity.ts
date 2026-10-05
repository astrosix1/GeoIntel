// The strict five-level scale; the backend (services/severity.py) scores to the same bands.
export const SEVERITY_BANDS = [
  { min: 80, label: 'Critical', color: '#dc2626' },
  { min: 60, label: 'Severe', color: '#f97316' },
  { min: 40, label: 'Serious', color: '#eab308' },
  { min: 20, label: 'Moderate', color: '#84cc16' },
  { min: 0, label: 'Minor', color: '#22c55e' },
] as const;

function bandFor(severity: number) {
  return SEVERITY_BANDS.find((band) => severity >= band.min) ?? SEVERITY_BANDS[SEVERITY_BANDS.length - 1];
}

export function colorForSeverity(severity: number): string {
  return bandFor(severity).color;
}

export function labelForSeverity(severity: number): string {
  return bandFor(severity).label;
}
