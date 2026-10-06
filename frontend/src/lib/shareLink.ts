// Shareable links for Weather mode: a URL that opens the map on one hazard or one place.
// Links carry only an id or coordinates, never anything personal, and are validated on the way
// in, since anyone can type one.
const HAZARD_TYPES = ['TC', 'FL', 'WF', 'DR'];
const LABEL_MAX = 80;

export type ShareTarget =
  | { kind: 'hazard'; eventType: string; id: number }
  | { kind: 'point'; lat: number; lon: number; label: string | null };

export function buildShareUrl(target: ShareTarget, base: string = window.location.origin + window.location.pathname): string {
  const params = new URLSearchParams({ view: 'weather' });
  if (target.kind === 'hazard') {
    params.set('hazard', `${target.eventType}-${target.id}`);
  } else {
    params.set('lat', (Math.round(target.lat * 10000) / 10000).toString());
    params.set('lon', (Math.round(target.lon * 10000) / 10000).toString());
    if (target.label) params.set('label', target.label.slice(0, LABEL_MAX));
  }
  return `${base}?${params.toString()}`;
}

// The target a link asks for, or null when the query holds nothing usable (or something invalid).
export function parseShareTarget(search: string): ShareTarget | null {
  const params = new URLSearchParams(search);
  if (params.get('view') !== 'weather') return null;
  const hazard = params.get('hazard');
  if (hazard) {
    const match = /^([A-Z]{2})-(\d{1,12})$/.exec(hazard);
    if (!match || !HAZARD_TYPES.includes(match[1])) return null;
    return { kind: 'hazard', eventType: match[1], id: Number(match[2]) };
  }
  const lat = Number(params.get('lat'));
  const lon = Number(params.get('lon'));
  if (params.get('lat') === null || params.get('lon') === null) return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  const label = (params.get('label') ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, LABEL_MAX);
  return { kind: 'point', lat, lon, label: label || null };
}

// Removes the link's parameters from the address bar once they have been applied.
export function clearShareParams(): void {
  try {
    window.history.replaceState(null, '', window.location.pathname);
  } catch {
    /* ignore: the address bar just keeps the parameters */
  }
}
