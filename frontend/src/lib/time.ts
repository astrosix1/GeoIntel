// "just now", "5 min ago", "3 h ago", "2 d ago", else a short date.
export function timeAgo(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(then).toLocaleDateString();
}

// "now", "5m", "3h", "2d": the shortest honest age, for dense list rows. A time in the future reads as "now".
export function shortAge(then: Date | null, now: number = Date.now()): string {
  if (!then || Number.isNaN(then.getTime())) return '';
  const seconds = Math.max(0, Math.round((now - then.getTime()) / 1000));
  if (seconds < 60) return 'now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return days < 100 ? `${days}d` : '99d+';
}
