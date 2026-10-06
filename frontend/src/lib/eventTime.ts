// The local time of day at an event's pin when its first report appeared.
//
// What the time means matters here. GDELT's timestamp is when its first article about the event was added to the
// feed, not when the incident happened, so everything shown is worded "first reported", never "happened". Sources
// that give only a date (ACLED) have no time of day and are left out. This file imports only lib files so it can
// be unit-tested (frontend/tests/eventTime.test.ts).
import { localParts } from './planner.ts';

export const NIGHT_FROM_HOUR = 22;
export const NIGHT_UNTIL_HOUR = 5;
// The feed's own position confidence for a city-level pin (see lib/precision.ts); a coarser pin is only approximate.
export const CITY_LEVEL_CONFIDENCE = 85;

export function isNightHour(hour: number): boolean {
  return hour >= NIGHT_FROM_HOUR || hour < NIGHT_UNTIL_HOUR;
}

// The backend sends UTC times without a zone suffix ("2026-10-05T15:45:00"); read them as UTC.
export function parseUtc(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const date = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

// Only GDELT events carry a time of day (their ids start "gdelt_").
export function hasReportTime(id: string): boolean {
  return id.startsWith('gdelt_');
}

export interface ReportedLocalTime {
  time: string;          // "02:40"
  night: boolean;
  // True when the pin is only country or region level, so the zone (and the local time) may be off.
  approximate: boolean;
}

export function reportedLocalTime(
  dateIso: string | null | undefined,
  tzid: string,
  locationConfidence: number | null | undefined,
): ReportedLocalTime | null {
  const at = parseUtc(dateIso);
  if (!at) return null;
  try {
    const p = localParts(tzid, at);
    return {
      time: `${String(p.hour).padStart(2, '0')}:${String(p.minute).padStart(2, '0')}`,
      night: isNightHour(p.hour),
      approximate: (locationConfidence ?? 0) < CITY_LEVEL_CONFIDENCE,
    };
  } catch {
    return null;
  }
}
