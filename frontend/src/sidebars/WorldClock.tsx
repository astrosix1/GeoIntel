import { useMemo, useState } from 'react';
import { MAX_CLOCKS } from '../lib/clocks';
import { cityName, formatOffset, offsetMinutes, readClock, regionName, searchZones } from '../lib/timezones';
import { useShownNow } from '../state/useNow';
import { useUiStore } from '../state/uiStore';
import sidebar from './EventsSidebar.module.css';
import styles from './WorldClock.module.css';

// Time Zone mode's left panel: clocks for the places the user pinned, with the clock display options.
// Everything is computed in the browser from its own tz database; nothing is fetched or invented.
export default function WorldClock() {
  const clocks = useUiStore((s) => s.clocks);
  const prefs = useUiStore((s) => s.clockPrefs);
  const addClock = useUiStore((s) => s.addClock);
  const removeClock = useUiStore((s) => s.removeClock);
  const setPrefs = useUiStore((s) => s.setClockPrefs);
  const selectZone = useUiStore((s) => s.selectZone);
  const now = useShownNow();
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchZones(query).filter((z) => !clocks.includes(z)), [query, clocks]);
  const full = clocks.length >= MAX_CLOCKS;

  return (
    <>
      <div className={sidebar.header}>World clock{offset !== 0 ? ' (chosen time, not now)' : ''}</div>
      <div className={styles.controls}>
        <span className={styles.toggle} role="group" aria-label="Hour format">
          {[false, true].map((h12) => (
            <button
              key={String(h12)}
              type="button"
              aria-pressed={prefs.hour12 === h12}
              className={`${styles.toggleButton} ${prefs.hour12 === h12 ? styles.toggleActive : ''}`}
              onClick={() => setPrefs({ ...prefs, hour12: h12 })}
            >
              {h12 ? '12 hour' : '24 hour'}
            </button>
          ))}
        </span>
        <span className={styles.toggle} role="group" aria-label="Date format">
          {(['long', 'iso'] as const).map((format) => (
            <button
              key={format}
              type="button"
              aria-pressed={prefs.dateFormat === format}
              className={`${styles.toggleButton} ${prefs.dateFormat === format ? styles.toggleActive : ''}`}
              onClick={() => setPrefs({ ...prefs, dateFormat: format })}
            >
              {format === 'long' ? 'Wed, Oct 7' : '2026-10-07'}
            </button>
          ))}
        </span>
      </div>

      <div className={styles.search}>
        <input
          className={styles.searchInput}
          type="search"
          value={query}
          placeholder={full ? `Clock limit reached (${MAX_CLOCKS})` : 'Add a city, e.g. Tokyo'}
          disabled={full}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search for a city to add a clock"
        />
        {results.length > 0 && (
          <ul className={styles.results}>
            {results.map((zone) => (
              <li key={zone}>
                <button
                  type="button"
                  className={styles.result}
                  onClick={() => {
                    addClock(zone);
                    setQuery('');
                  }}
                >
                  {cityName(zone)} <span className={styles.resultMeta}>{regionName(zone)} · {zone}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {query.trim().length >= 2 && results.length === 0 && <div className={styles.note}>No matching city.</div>}
      </div>

      <div className={sidebar.list}>
        {clocks.length === 0 && (
          <div className={styles.note}>
            Pin up to {MAX_CLOCKS} places to keep their clocks here. Search above, or click a zone on the globe and pin it
            from its panel.
          </div>
        )}
        {clocks.map((tzid) => {
          const reading = readClock(tzid, now, prefs);
          return (
            <div key={tzid} className={styles.clock}>
              <button type="button" className={styles.clockMain} onClick={() => selectZone(tzid)}>
                <div className={styles.city}>{cityName(tzid)}</div>
                <div className={styles.meta}>
                  {reading ? reading.date : 'Unknown zone'} · {formatOffset(offsetMinutes(tzid, now))}
                </div>
              </button>
              <div className={styles.time}>
                {reading?.time ?? '–'}
                {reading && reading.day !== 'today' && <span className={styles.day}>{reading.day}</span>}
              </div>
              <button type="button" className={styles.remove} aria-label={`Remove ${cityName(tzid)}`} onClick={() => removeClock(tzid)}>
                ×
              </button>
            </div>
          );
        })}
        {clocks.length > 0 && (
          <div className={styles.note}>
            &ldquo;Tomorrow&rdquo; and &ldquo;yesterday&rdquo; compare each place&apos;s date with the date in UTC right now.
          </div>
        )}
      </div>
    </>
  );
}
