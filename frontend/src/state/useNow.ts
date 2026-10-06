import { useEffect, useState } from 'react';
import { useUiStore } from './uiStore';

// The current time, refreshed every second so clocks tick. Clocks show minutes, so a second's
// resolution is more than enough, and one shared interval per component is cheap.
export function useNow(intervalMs = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

// The moment Time Zone mode is showing: now, moved by the time slider. Clocks, the zone panel and the
// night shading all use this, so they always agree with each other.
export function useShownNow(): Date {
  const now = useNow();
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  return new Date(now.getTime() + offset * 60_000);
}
