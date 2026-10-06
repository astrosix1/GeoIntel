import { useMemo, useState } from 'react';
import CopyLinkButton from '../components/CopyLinkButton';
import { MAX_CLOCKS } from '../lib/clocks';
import { nextChangeShort } from '../lib/dst';
import { cityName, formatOffset, offsetMinutes, readClock, regionName, searchZones } from '../lib/timezones';
import { useShownNow } from '../state/useNow';
import { useUiStore } from '../state/uiStore';
import { IconButton } from '../ui/Button';
import { Badge, StateMessage, Tabs } from '../ui/Display';
import ConverterPanel from './ConverterPanel';
import PlannerPanel from './PlannerPanel';
import sidebar from './EventsSidebar.module.css';
import styles from './WorldClock.module.css';

type Tab = 'clocks' | 'planner' | 'convert';
const TABS: { id: Tab; label: string }[] = [
  { id: 'clocks', label: 'Clocks' },
  { id: 'planner', label: 'Meeting planner' },
  { id: 'convert', label: 'Convert' },
];

// Time Zone mode's left panel: clocks for the places the user pinned, a meeting planner and a time converter. Everything is
// computed in the browser from its own tz database; nothing is fetched or invented.
export default function WorldClock() {
  const clocks = useUiStore((s) => s.clocks);
  const prefs = useUiStore((s) => s.clockPrefs);
  const addClock = useUiStore((s) => s.addClock);
  const removeClock = useUiStore((s) => s.removeClock);
  const selectZone = useUiStore((s) => s.selectZone);
  const offset = useUiStore((s) => s.timeOffsetMinutes);
  const shared = useUiStore((s) => s.sharedClocks);
  const keepShared = useUiStore((s) => s.keepSharedClocks);
  const notice = useUiStore((s) => s.zoneNotice);
  const setNotice = useUiStore((s) => s.setZoneNotice);
  const now = useShownNow();
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<Tab>('clocks');
  const results = useMemo(() => searchZones(query).filter((z) => !clocks.includes(z)), [query, clocks]);
  const full = clocks.length >= MAX_CLOCKS;
  // The next clock change only moves once a day, so it is worked out once a day.
  const dayKey = Math.floor(now.getTime() / 86_400_000);
  const dayMiddle = new Date(dayKey * 86_400_000 + 43_200_000);

  return (
    <>
      <div className={sidebar.head}>
        <span className={sidebar.title}>World clock</span>
        <span className={sidebar.count}>{clocks.length}</span>
        <span className={sidebar.grow} />
        {offset !== 0 && tab === 'clocks' && <Badge tone="warn">Chosen time, not now</Badge>}
      </div>
      <div className={styles.tabs}>
        <Tabs label="World clock views" tabs={TABS} value={tab} onChange={setTab} />
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
            {query.trim().length >= 2 && results.length === 0 && <p className={styles.note}>No matching city.</p>}
          </div>

          {notice && (
            <p className={styles.noteWarn}>
              {notice}{' '}
              <button type="button" className={styles.link} onClick={() => setNotice(null)}>Dismiss</button>
            </p>
          )}
          {shared && (
            <p className={styles.note}>
              These clocks came from a shared link and are not saved.{' '}
              <button type="button" className={styles.link} onClick={keepShared}>Keep them</button>
            </p>
          )}

          <div className={styles.list}>
            {clocks.length === 0 && (
              <StateMessage
                kind="empty"
                title="No clocks pinned"
                hint={`Pin up to ${MAX_CLOCKS} places. Search above, or click a zone on the globe and pin it from its panel.`}
              />
            )}
            {clocks.map((tzid) => {
              const reading = readClock(tzid, now, prefs);
              return (
                <div key={tzid} className={styles.clock}>
                  <button type="button" className={styles.clockMain} onClick={() => selectZone(tzid)}>
                    <span className={styles.city}>{cityName(tzid)}</span>
                    <span className={styles.meta}>{formatOffset(offsetMinutes(tzid, now))} · {nextChangeShort(tzid, dayMiddle)}</span>
                  </button>
                  <span className={styles.timeBlock}>
                    <span className={styles.time}>{reading?.time ?? '–'}</span>
                    <span className={styles.meta}>
                      {reading ? reading.date : 'Unknown zone'}
                      {reading && reading.day !== 'today' && <span className={styles.day}>{reading.day}</span>}
                    </span>
                  </span>
                  <IconButton icon="close" size="sm" label={`Remove ${cityName(tzid)}`} onClick={() => removeClock(tzid)} />
                </div>
              );
            })}
          </div>
          {clocks.length > 0 && (
            <div className={styles.footer}>
              <CopyLinkButton className={styles.link} target={{ kind: 'clocks', zones: clocks, skipped: 0 }} />
              <span className={styles.note}>&ldquo;Tomorrow&rdquo; and &ldquo;yesterday&rdquo; compare each date with the date in UTC.</span>
            </div>
          )}
        </>
      )}
    </>
  );
}
