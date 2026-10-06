import { useEffect, useState } from 'react';

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
