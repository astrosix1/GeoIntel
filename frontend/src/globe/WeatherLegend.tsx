import { useRadarFramesQuery, useStormsQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import { HAZARD_TYPES } from './hazards';
import { radarCanAnimate } from './useRadar';
import styles from './WeatherLegend.module.css';

// Weather mode's filter row: one chip per hazard type with its live count.
// Also the place that says so honestly when the feed is loading, down, or
// genuinely empty — the globe alone would just look blank.
export default function WeatherLegend() {
  const activeMode = useUiStore((s) => s.activeMode);
  const tab = useUiStore((s) => s.weatherTab);
  const category = useUiStore((s) => s.weatherCategory);
  const setTab = useUiStore((s) => s.setWeatherTab);
  const setCategory = useUiStore((s) => s.setWeatherCategory);
  const { data, isLoading, isError, refetch } = useStormsQuery(activeMode === 'weather');
  const radarOn = useUiStore((s) => s.radarOn);
  const setRadarOn = useUiStore((s) => s.setRadarOn);
  const radarPlaying = useUiStore((s) => s.radarPlaying);
  const setRadarPlaying = useUiStore((s) => s.setRadarPlaying);
  const radarTime = useUiStore((s) => s.radarTime);
  const radarError = useRadarFramesQuery(activeMode === 'weather' && radarOn).isError;

  if (activeMode !== 'weather') return null;

  // A chip is the quick way into the list's Categories filter: click to show
  // only that hazard type, click again to show everything.
  function pick(code: string) {
    if (tab === 'categories' && category === code) {
      setTab('all');
      setCategory(null);
    } else {
      setTab('categories');
      setCategory(code);
    }
  }

  const counts = new Map<string, number>();
  data?.storms.forEach((s) => counts.set(s.event_type, (counts.get(s.event_type) ?? 0) + 1));

  return (
    <div className={styles.legend} data-ui-hover-surface>
      <div className={styles.chips}>
        {HAZARD_TYPES.map((type) => {
          const off = tab === 'categories' && category !== null && category !== type.code;
          return (
            <button
              key={type.code}
              type="button"
              aria-pressed={!off}
              className={`${styles.chip} ${off ? styles.chipOff : ''}`}
              onClick={() => pick(type.code)}
            >
              <span aria-hidden="true">{type.icon}</span> {type.label}
              {data && <span className={styles.count}>{counts.get(type.code) ?? 0}</span>}
            </button>
          );
        })}
        <button
          type="button"
          aria-pressed={radarOn}
          className={`${styles.chip} ${radarOn ? '' : styles.chipOff}`}
          onClick={() => setRadarOn(!radarOn)}
        >
          <span aria-hidden="true">📡</span> Radar
        </button>
        {radarOn && radarCanAnimate() && (
          <button
            type="button"
            className={styles.chip}
            aria-label={radarPlaying ? 'Pause radar loop' : 'Play radar loop'}
            onClick={() => setRadarPlaying(!radarPlaying)}
          >
            {radarPlaying ? '⏸' : '▶'}
          </button>
        )}
      </div>
      {radarOn && (radarTime || radarError) && (
        <div className={styles.note}>
          {radarError
            ? "Radar isn't available right now."
            : `Radar ${new Date((radarTime as number) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · past 2 hours`}
        </div>
      )}
      <div className={styles.note}>
        {isLoading && 'Loading active events…'}
        {isError && (
          <>
            Live hazard data isn&apos;t available right now.{' '}
            <button type="button" className={styles.retry} onClick={() => refetch()}>
              Try again
            </button>
          </>
        )}
        {data && data.count === 0 && 'No active weather hazards reported right now.'}
        {data && data.count > 0 && 'Live data from GDACS. Click a pin for details.'}
      </div>
    </div>
  );
}
