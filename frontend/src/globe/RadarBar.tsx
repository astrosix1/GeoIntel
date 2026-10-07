import { radarCanAnimate } from './useRadar';
import { useRadarFramesQuery } from '../state/queries';
import { useDrawStore } from '../state/drawStore';
import { useUiStore } from '../state/uiStore';
import { IconButton } from '../ui/Button';
import Button from '../ui/Button';
import styles from './TimeBar.module.css';

function minutesAgo(time: number, newest: number): string {
  const minutes = Math.round((newest - time) / 60);
  return minutes <= 0 ? 'latest' : `${minutes} min earlier`;
}

// Weather mode's radar timeline: play or pause the loop, or drag to any radar frame of the past two hours. It shares the
// look of the Time Zone mode's time bar. A shifted frame says so; "Latest" jumps back to the newest.
export default function RadarBar() {
  const activeMode = useUiStore((s) => s.activeMode);
  const radarOn = useUiStore((s) => s.radarOn);
  const playing = useUiStore((s) => s.radarPlaying);
  const setPlaying = useUiStore((s) => s.setRadarPlaying);
  const cursor = useUiStore((s) => s.radarCursor);
  const setCursor = useUiStore((s) => s.setRadarCursor);
  const times = useUiStore((s) => s.radarFrameTimes);
  const presenting = useDrawStore((s) => s.presenting);
  const failed = useRadarFramesQuery(radarOn && activeMode === 'weather').isError;
  if (presenting || activeMode !== 'weather' || !radarOn || failed || times.length === 0) return null;

  const last = times.length - 1;
  const index = Math.min(cursor, last);
  const time = times[index];
  const canAnimate = radarCanAnimate();
  const clock = new Date(time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const isLatest = index === last;

  return (
    <div className={styles.bar} data-ui-hover-surface>
      {canAnimate && (
        <IconButton
          icon={playing ? 'pause' : 'play'}
          label={playing ? 'Pause the radar loop' : 'Play the radar loop'}
          size="sm"
          onClick={() => setPlaying(!playing)}
        />
      )}
      <div className={styles.middle}>
        <input
          className={styles.slider}
          type="range"
          min={0}
          max={Math.max(last, 1)}
          step={1}
          value={index}
          disabled={last < 1}
          onChange={(e) => {
            setPlaying(false);
            setCursor(Number(e.target.value));
          }}
          aria-label="Choose a radar frame from the past two hours"
          aria-valuetext={`${clock}, ${minutesAgo(time, times[last])}`}
        />
        <div className={`${styles.readout} ${isLatest ? '' : styles.shifted}`}>
          Radar {clock} · {isLatest ? 'latest frame' : minutesAgo(time, times[last])}
          {last < 1 && ' · this device shows the latest frame only'}
        </div>
      </div>
      <Button
        size="sm"
        disabled={isLatest}
        onClick={() => {
          setPlaying(false);
          setCursor(Number.MAX_SAFE_INTEGER);
        }}
      >
        Latest
      </Button>
    </div>
  );
}
