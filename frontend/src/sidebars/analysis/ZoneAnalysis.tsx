import { useMemo } from 'react';
import { MAX_CLOCKS } from '../../lib/clocks';
import { cityName, isKnownZone, readClock, regionName, zoneInfo, zonesLike } from '../../lib/timezones';
import { useNow } from '../../state/useNow';
import { useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';
import forecastStyles from './PointForecast.module.css';
import hazardStyles from './HazardAnalysis.module.css';

const SHOWN_PLACES = 30;

function dstText(pattern: 'none' | 'dst' | 'irregular', dstNow: boolean): string {
  if (pattern === 'dst') return dstNow ? 'Observes daylight saving, in effect now' : 'Observes daylight saving, not in effect now';
  if (pattern === 'irregular') return 'Offset changes for a few weeks of the year';
  return 'No daylight saving';
}

// Analysis view for a clicked time zone: its offset, daylight-saving behaviour, current local time and the
// other places the browser's tz database lists with the same rules. The map boundary names one representative
// zone id for each area, so the places that share its rules are listed beneath it.
export default function ZoneAnalysis({ tzid }: { tzid: string }) {
  const now = useNow();
  const clocks = useUiStore((s) => s.clocks);
  const prefs = useUiStore((s) => s.clockPrefs);
  const addClock = useUiStore((s) => s.addClock);
  const removeClock = useUiStore((s) => s.removeClock);
  const known = isKnownZone(tzid);
  const info = zoneInfo(tzid, now);
  const reading = readClock(tzid, now, prefs);
  const utcReading = readClock('UTC', now, prefs);
  // The slow part (it samples every zone once), so it is done once per zone, not on every tick.
  const places = useMemo(() => zonesLike(tzid, new Date()).map(cityName).sort(), [tzid]);
  const pinned = clocks.includes(tzid);

  if (!known) return <div className={styles.loading}>That time zone isn&apos;t recognised by this browser.</div>;

  return (
    <div>
      <h2 className={styles.title}>{info.city}</h2>
      <div className={styles.metaRow}>
        <span className={styles.badge}>{info.offsetLabel}</span>
        {regionName(tzid) && <span className={styles.badge}>{regionName(tzid)}</span>}
        <span className={styles.badge}>{tzid}</span>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Local time</div>
        <div style={{ fontSize: 28, fontVariantNumeric: 'tabular-nums' }}>{reading?.time ?? '–'}</div>
        <div className={styles.mediaCaption}>
          {reading?.date}
          {reading && reading.day !== 'today' ? ` (${reading.day} in UTC terms)` : ''} · UTC is {utcReading?.time}
        </div>
        <div style={{ marginTop: 8 }}>
          {pinned ? (
            <button type="button" className={forecastStyles.watchButton} onClick={() => removeClock(tzid)}>
              Remove from my clocks
            </button>
          ) : (
            <button
              type="button"
              className={forecastStyles.watchButton}
              disabled={clocks.length >= MAX_CLOCKS}
              onClick={() => addClock(tzid)}
            >
              {clocks.length >= MAX_CLOCKS ? `Clock limit reached (${MAX_CLOCKS})` : '+ Pin this clock'}
            </button>
          )}
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Rules</div>
        <dl className={hazardStyles.facts}>
          <dt>Offset now</dt>
          <dd>{info.offsetLabel}</dd>
          <dt>Daylight saving</dt>
          <dd>{dstText(info.pattern, info.dstNow)}</dd>
        </dl>
      </div>

      {places.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Same rules all year ({places.length} more)</div>
          <div className={styles.briefingText}>
            {places.slice(0, SHOWN_PLACES).join(', ')}
            {places.length > SHOWN_PLACES ? `, and ${places.length - SHOWN_PLACES} more` : ''}
          </div>
        </div>
      )}

      <div className={styles.mediaCaption}>
        Times come from your browser&apos;s own time zone database, so they follow daylight saving correctly. The map
        boundaries are simplified from OpenStreetMap-based data and merge zones that currently share the same rules, so a
        place near a boundary may sit on the other side of the line. The place list is the zone names in that database; it
        is not ranked by population and carries no country information.
      </div>
    </div>
  );
}
