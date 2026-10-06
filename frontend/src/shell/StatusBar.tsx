import { timeAgo } from '../lib/time';
import { useStormsQuery, useVisibleCrises } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import { useNow } from '../state/useNow';
import styles from './Bar.module.css';

function utcClock(now: Date): string {
  return `${String(now.getUTCHours()).padStart(2, '0')}:${String(now.getUTCMinutes()).padStart(2, '0')}`;
}

// The one place that says how fresh the data is and whether something is wrong with it. (It replaces notes that used to
// appear in different corners of different screens.)
export default function StatusBar() {
  const mode = useUiStore((s) => s.activeMode);
  const scope = useUiStore((s) => s.scope);
  const timeRange = useUiStore((s) => s.timeRange);
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  const crises = useVisibleCrises(scope, timeRange);
  const storms = useStormsQuery(mode === 'weather');
  const now = useNow(15_000);

  let text = '';
  let problem = false;
  if (mode === 'events') {
    if (crises.isError && !crises.data) {
      text = 'Events are unavailable right now.';
      problem = true;
    } else if (crises.isLoading) text = 'Loading events…';
    else if (crises.data) {
      text = `${crises.data.length.toLocaleString()} events · updated ${crises.dataUpdatedAt ? timeAgo(new Date(crises.dataUpdatedAt).toISOString()) : 'just now'}`;
      if (crises.isError) {
        text += ' · refresh failed, showing the last data';
        problem = true;
      }
    }
  } else if (mode === 'weather') {
    if (storms.isError && !storms.data) {
      text = 'Hazard data is unavailable right now.';
      problem = true;
    } else if (storms.isLoading) text = 'Loading hazards…';
    else if (storms.data) text = `${storms.data.count} active hazards · checked ${timeAgo(storms.data.generated_at)}`;
  } else {
    text = offset === 0 ? 'Showing the time now' : `Showing a chosen time (${offset > 0 ? '+' : '-'}${Math.abs(offset) / 60} h from now), not now`;
    problem = offset !== 0;
  }

  return (
    <footer className={styles.status}>
      <span className={problem ? styles.statusError : undefined} role="status">{text}</span>
      <span>UTC {utcClock(now)}</span>
    </footer>
  );
}
