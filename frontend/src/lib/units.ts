// Display units for forecasts. The API is metric; this converts for display
// and remembers the choice (best effort: storage can be blocked).
export type UnitSystem = 'metric' | 'imperial';

const KEY = 'geointel.units';

export function loadUnits(): UnitSystem {
  try {
    return localStorage.getItem(KEY) === 'imperial' ? 'imperial' : 'metric';
  } catch {
    return 'metric';
  }
}

export function saveUnits(units: UnitSystem): void {
  try {
    localStorage.setItem(KEY, units);
  } catch {
    /* storage unavailable: the choice just lasts for this visit */
  }
}

export function formatTemp(celsius: number | null | undefined, units: UnitSystem): string {
  if (celsius == null) return '–';
  return units === 'imperial' ? `${Math.round((celsius * 9) / 5 + 32)}°F` : `${Math.round(celsius)}°C`;
}

export function formatSpeed(kmh: number | null | undefined, units: UnitSystem): string {
  if (kmh == null) return '–';
  return units === 'imperial' ? `${Math.round(kmh * 0.621371)} mph` : `${Math.round(kmh)} km/h`;
}

export function formatRain(mm: number | null | undefined, units: UnitSystem): string {
  if (mm == null) return '–';
  return units === 'imperial' ? `${(mm / 25.4).toFixed(2)} in` : `${mm.toFixed(1)} mm`;
}

export function formatDistance(meters: number | null | undefined, units: UnitSystem): string {
  if (meters == null) return '–';
  const km = meters / 1000;
  return units === 'imperial' ? `${(km * 0.621371).toFixed(1)} mi` : `${km.toFixed(1)} km`;
}

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
export function compass(degrees: number | null | undefined): string {
  if (degrees == null) return '';
  return COMPASS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16];
}
