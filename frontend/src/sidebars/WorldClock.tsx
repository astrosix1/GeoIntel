import { useMemo, useState } from 'react';
import CopyLinkButton from '../components/CopyLinkButton';
import { MAX_CLOCKS } from '../lib/clocks';
import { nextChangeLine } from '../lib/dst';
import { cityName, formatOffset, offsetMinutes, readClock, regionName, searchZones } from '../lib/timezones';
import { useShownNow } from '../state/useNow';
import { useUiStore } from '../state/uiStore';
import ConverterPanel from './ConverterPanel';
import PlannerPanel from './PlannerPanel';
import sidebar from './EventsSidebar.module.css';
import planner from './Planner.module.css';
import styles from './WorldClock.module.css';

// Time Zone mode's left panel: clocks for the places the user pinned, with the clock display options.
// Everything is computed in the browser from its own tz database; nothing is fetched or invented.
type Tab = 'clocks' | 'planner' | 'convert';
const TABS: { value: Tab; label: string }[] = [
  { value: 'clocks', label: 'Clocks' },
  { value: 'planner', label: 'Meeting planner' },
  { value: 'convert', label: 'Convert' },
];

export default function WorldClock() {
  const clocks = useUiStore((s) => s.clocks);
  const prefs = useUiStore((s) => s.clockPrefs);
  const addClock = useUiStore((s) => s.addClock);
  const removeClock = useUiStore((s) => s.removeClock);
  const selectZone = useUiStore((s) => s.selectZone);
  const now = useShownNow();
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  const shared = useUiStore((s) => s.sharedClocks);
  const keepShared = useUiStore((s) => s.keepSharedClocks);
  const notice = useUiStore((s) => s.zoneNotice);
  const setNotice = useUiStore((s) => s.setZoneNotice);
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<Tab>('clocks');
  const results = useMemo(() => searchZones(query).filter((z) => !clocks.includes(z)), [query, clocks]);
  const full = clocks.length >= MAX_CLOCKS;
  // The next clock change only moves once a day, so it is worked out once a day.
  const dayKey = Math.floor(now.getTime() / 86_400_000);

  return (
    <>
      <div className={sidebar.header}>World clock{offset !== 0 && tab === 'clocks' ? ' (chosen time, not now)' : ''}</div>
      <div className={planner.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            className={`${planner.tab} ${tab === t.value ? planner.tabActive : ''}`}
            onClick={() => setTab(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'planner' && <PlannerPanel />}
      {tab === 'convert' && <ConverterPanel />}
      {tab === 'clocks' && (
        <>
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

      {notice && (
        <div className={styles.note}>
          {notice}{' '}
          <button type="button" className={styles.remove} style={{ fontSize: 12 }} onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {shared && (
        <div className={styles.note}>
          These clocks came from a shared link and are not saved.{' '}
          <button type="button" className={styles.remove} style={{ fontSize: 12, textDecoration: 'underline' }} onClick={keepShared}>
            Keep them
          </button>
        </div>
      )}

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
                <div className={styles.meta}>{nextChangeLine(tzid, new Date(dayKey * 86_400_000 + 43_200_000))}</div>
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
            <CopyLinkButton className={styles.remove} target={{ kind: 'clocks', zones: clocks, skipped: 0 }} />{' '}
            &ldquo;Tomorrow&rdquo; and &ldquo;yesterday&rdquo; compare each place&apos;s date with the date in UTC right now.
          </div>
        )}
      </div>
        </>
      )}
    </>
  );
}
