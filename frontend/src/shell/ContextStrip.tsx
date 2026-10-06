import { HAZARD_TYPES } from '../globe/hazards';
import { timeAgo } from '../lib/time';
import { useRadarFramesQuery, useStormsQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import { Chip } from '../ui/Display';
import styles from './Bar.module.css';

// A thin strip under the top bar with whatever belongs to the current mode: in Events, the key to how pins are drawn;
// in Weather, the hazard-type chips and the honest notices (loading, feed down, nothing active, radar unavailable);
// in Time Zone, nothing (its time control sits on the map).
export default function ContextStrip() {
  const mode = useUiStore((s) => s.activeMode);
  if (mode === 'events') return <EventsKey />;
  if (mode === 'weather') return <WeatherStrip />;
  return null;
}

function EventsKey() {
  return (
    <div className={styles.strip}>
      <div className={styles.key}>
        <span className={styles.keyItem}><span className={`${styles.dot} ${styles.dotSolid}`} aria-hidden="true" />Something that happened</span>
        <span className={styles.keyItem}><span className={`${styles.dot} ${styles.dotHollow}`} aria-hidden="true" />A statement or talks (no physical place)</span>
        <span className={styles.keyItem}><span className={`${styles.dot} ${styles.dotRing}`} aria-hidden="true" />Ring: approximate area, wider is less precise</span>
      </div>
    </div>
  );
}

function WeatherStrip() {
  const tab = useUiStore((s) => s.weatherTab);
  const category = useUiStore((s) => s.weatherCategory);
  const setTab = useUiStore((s) => s.setWeatherTab);
  const setCategory = useUiStore((s) => s.setWeatherCategory);
  const radarOn = useUiStore((s) => s.radarOn);
  const radarTime = useUiStore((s) => s.radarTime);
  const notice = useUiStore((s) => s.weatherNotice);
  const setNotice = useUiStore((s) => s.setWeatherNotice);
  const { data, isLoading, isError, refetch } = useStormsQuery(true);
  const radarError = useRadarFramesQuery(radarOn).isError;

  // A chip is the quick way into the list's Categories filter: click to show only that hazard type, click again for all.
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
    <div className={styles.strip}>
      <div className={styles.stripChips}>
        {HAZARD_TYPES.map((type) => {
          const off = tab === 'categories' && category !== null && category !== type.code;
          return (
            <Chip key={type.code} pressed={!off} onClick={() => pick(type.code)} count={data ? counts.get(type.code) ?? 0 : undefined}>
              {type.label}
            </Chip>
          );
        })}
      </div>
      {radarOn && radarError && <span className={styles.noteWarn}>Radar isn&apos;t available right now.</span>}
      {radarOn && !radarError && radarTime && (
        <span className={styles.note}>
          Radar {new Date(radarTime * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · past 2 hours
        </span>
      )}
      {notice && (
        <span className={styles.noteWarn}>
          {notice}{' '}
          <button type="button" className={styles.link} onClick={() => setNotice(null)}>Dismiss</button>
        </span>
      )}
      {isLoading && <span className={styles.note}>Loading active events…</span>}
      {isError && (
        <span className={styles.noteWarn}>
          Live hazard data isn&apos;t available right now.{' '}
          <button type="button" className={styles.link} onClick={() => refetch()}>Try again</button>
        </span>
      )}
      {data && data.count === 0 && <span className={styles.note}>No active weather hazards reported right now.</span>}
      {data && data.count > 0 && <span className={styles.note}>Live data from GDACS, checked {timeAgo(data.generated_at)}. Click a pin for details.</span>}
    </div>
  );
}
