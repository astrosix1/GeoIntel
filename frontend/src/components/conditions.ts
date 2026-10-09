import type { ConditionKey } from '../api/types';

// The forecast limits a user can switch on. Ranges match the server's own validation (services/condition_alerts.py).
export const CONDITIONS: { key: ConditionKey; label: string; unit: string; fallback: number; min: number; max: number }[] = [
  { key: 'heat_c', label: 'Heat: daily high at or above', unit: '°C', fallback: 38, min: 25, max: 55 },
  { key: 'cold_c', label: 'Cold: daily low at or below', unit: '°C', fallback: -10, min: -60, max: 10 },
  { key: 'rain_mm', label: 'Heavy rain: daily total at or above', unit: 'mm', fallback: 50, min: 10, max: 500 },
  { key: 'gust_kmh', label: 'Strong gusts: at or above', unit: 'km/h', fallback: 90, min: 50, max: 250 },
  { key: 'uv_index', label: 'UV index at or above', unit: '', fallback: 8, min: 6, max: 16 },
];
