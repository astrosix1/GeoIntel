import { useMemo } from 'react';
import { MAX_CLOCKS } from '../../lib/clocks';
import { cityName, isKnownZone, readClock, regionName, zoneInfo, zonesLike } from '../../lib/timezones';
import CopyLinkButton from '../../components/CopyLinkButton';
import { clockChanges, describeChange } from '../../lib/dst';
import { unusualOffsetNote } from '../../lib/zoneLabels';
import { sunAltitude, sunTimes } from '../../lib/sun';
import { useShownNow } from '../../state/useNow';
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

function hoursAndMinutes(hours: number): string {
  const total = Math.round(hours * 60);
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, '0')} min`;
}

// Sunrise, sunset and day length at the clicked point, in the zone's own time. Worked out from the date alone,
// so it is good to about a minute, and polar day and polar night are stated rather than left blank.
function SunBlock({ tzid, point, at, hour12 }: { tzid: string; point: { lat: number; lon: number }; at: Date; hour12: boolean }) {
  const times = sunTimes(point.lat, point.lon, at);
  const altitude = sunAltitude(point.lat, point.lon, at);
  const fmt = (d: Date | null) =>
    d ? new Intl.DateTimeFormat('en-US', { timeZone: tzid, hour: '2-digit', minute: '2-digit', hour12 }).format(d) : '–';
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Sun at the clicked point</div>
      <dl className={hazardStyles.facts}>
        <dt>Now</dt>
        <dd>{altitude >= -0.833 ? `Sun is up (${Math.round(altitude)}° above the horizon)` : `Sun is down (${Math.round(-altitude)}° below the horizon)`}</dd>
        {times.status === 'normal' && (
          <>
            <dt>Sunrise</dt>
            <dd>{fmt(times.sunrise)}</dd>
            <dt>Sunset</dt>
            <dd>{fmt(times.sunset)}</dd>
            <dt>Daylight</dt>
            <dd>{hoursAndMinutes(times.dayLengthHours)}</dd>
          </>
        )}
        {times.status === 'polar-day' && (
          <>
            <dt>Daylight</dt>
            <dd>Polar day: the sun does not set today</dd>
          </>
        )}
        {times.status === 'polar-night' && (
          <>
            <dt>Daylight</dt>
            <dd>Polar night: the sun does not rise today</dd>
          </>
        )}
      </dl>
      <div className={styles.mediaCaption}>
        At {Math.abs(point.lat).toFixed(1)}°{point.lat >= 0 ? 'N' : 'S'}, {Math.abs(point.lon).toFixed(1)}°{point.lon >= 0 ? 'E' : 'W'}. Sunrise and sunset are for
        the solar day that contains the time shown, in this zone&apos;s time.
      </div>
    </div>
  );
}

// Analysis view for a clicked time zone: its offset, daylight-saving behaviour, current local time and the
// other places the browser's tz database lists with the same rules. The map boundary names one representative
// zone id for each area, so the places that share its rules are listed beneath it.
export default function ZoneAnalysis({ tzid, point }: { tzid: string; point?: { lat: number; lon: number } }) {
  const now = useShownNow();
  const offset = useUiStore((s) => s.timeOffsetMinutes);
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
  // Looked up once per zone and day, not on every tick.
  const dayKey = Math.floor(now.getTime() / 86_400_000);
  const changes = useMemo(() => clockChanges(tzid, new Date(dayKey * 86_400_000 + 43_200_000)), [tzid, dayKey]);

  if (!known) return <div className={styles.loading}>That time zone isn&apos;t recognised by this browser.</div>;

  return (
    <div>
      <h2 className={styles.title}>{info.city}</h2>
      <div className={styles.metaRow}>
        <span className={styles.badge}>{info.offsetLabel}</span>
        {regionName(tzid) && <span className={styles.badge}>{regionName(tzid)}</span>}
        <span className={styles.badge}>{tzid}</span>
        <CopyLinkButton className={styles.badge} target={{ kind: 'zone', tzid }} />
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Local time{offset !== 0 ? ' at the chosen time' : ''}</div>
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
        <div className={styles.sectionTitle}>Clock changes</div>
        <dl className={hazardStyles.facts}>
          <dt>Next</dt>
          <dd>{changes.next ? describeChange(tzid, changes.next) : 'None in the next 14 months'}</dd>
          <dt>Last</dt>
          <dd>{changes.previous ? describeChange(tzid, changes.previous) : 'None in the last 14 months'}</dd>
        </dl>
      </div>

      {point && <SunBlock tzid={tzid} point={point} at={now} hour12={prefs.hour12} />}

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Rules</div>
        <dl className={hazardStyles.facts}>
          <dt>Offset now</dt>
          <dd>{info.offsetLabel}</dd>
          <dt>Daylight saving</dt>
          <dd>{dstText(info.pattern, info.dstNow)}</dd>
        </dl>
        {unusualOffsetNote(info.offsetMinutes) && <div className={styles.mediaCaption}>{unusualOffsetNote(info.offsetMinutes)}</div>}
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
