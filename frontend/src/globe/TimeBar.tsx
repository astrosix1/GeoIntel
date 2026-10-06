import { MAX_TIME_OFFSET_MINUTES, useUiStore } from '../state/uiStore';
import { useShownNow } from '../state/useNow';
import styles from './TimeBar.module.css';

const STEP_MINUTES = 15;

function describeOffset(minutes: number): string {
  const sign = minutes > 0 ? '+' : '-';
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `${sign}${h}${m ? `:${String(m).padStart(2, '0')}` : ''} h`;
}

// Time Zone mode's time control: show the night side and the clocks at another moment, up to a day either way.
// Whenever it is not "now" it says so plainly, so a shifted view is never mistaken for the real present.
export default function TimeBar() {
  const activeMode = useUiStore((s) => s.activeMode);
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  const setOffset = useUiStore((s) => s.setTimeOffsetMinutes);
  const nightOn = useUiStore((s) => s.nightOn);
  const setNightOn = useUiStore((s) => s.setNightOn);
  const labelsOn = useUiStore((s) => s.zoneLabelsOn);
  const setLabelsOn = useUiStore((s) => s.setZoneLabelsOn);
  const shown = useShownNow();
  if (activeMode !== 'timezone') return null;

  const label = new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(shown);

  return (
    <div className={styles.bar} data-ui-hover-surface>
      <button type="button" aria-pressed={nightOn} className={`${styles.chip} ${nightOn ? '' : styles.chipOff}`} onClick={() => setNightOn(!nightOn)}>
        <span aria-hidden="true">🌙</span> Night
      </button>
      <button type="button" aria-pressed={labelsOn} className={`${styles.chip} ${labelsOn ? '' : styles.chipOff}`} onClick={() => setLabelsOn(!labelsOn)}>
        Labels
      </button>
      <div className={styles.middle}>
        <input
          className={styles.slider}
          type="range"
          min={-MAX_TIME_OFFSET_MINUTES}
          max={MAX_TIME_OFFSET_MINUTES}
          step={STEP_MINUTES}
          value={offset}
          onChange={(e) => setOffset(Number(e.target.value))}
          aria-label="Move the time shown, up to a day either way"
          aria-valuetext={offset === 0 ? 'Now' : `${describeOffset(offset)} from now`}
        />
        <div className={`${styles.readout} ${offset === 0 ? '' : styles.shifted}`}>
          {offset === 0 ? `Now · ${label} UTC` : `Showing ${label} UTC (${describeOffset(offset)}), not now`}
        </div>
      </div>
      <button type="button" className={styles.chip} disabled={offset === 0} onClick={() => setOffset(0)}>
        Now
      </button>
    </div>
  );
}
