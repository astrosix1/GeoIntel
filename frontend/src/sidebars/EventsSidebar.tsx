import { useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import SheetHandle from './SheetHandle';
import { useUiStore } from '../state/uiStore';
import type { EventsTab, TimeRange } from '../state/uiStore';
import { useStormsQuery, useVisibleCrises } from '../state/queries';
import { useReportedAtNight } from '../state/useZoneIndex';
import { hazardIconName, HAZARD_TYPES } from '../globe/hazards';
import { labelForSeverity, severityTone } from '../globe/severity';
import { TOPICS, TYPES_COVERED_BY_TOPICS, topicsOf, typeLabel } from '../lib/topics';
import { applyCrisisFilter, applyHazardFilter, defaultDirection, sortCrises } from '../lib/filters';
import type { CrisisSortKey } from '../lib/filters';
import { parseUtc } from '../lib/eventTime';
import { shortAge } from '../lib/time';
import type { Storm } from '../api/types';
import Button from '../ui/Button';
import { Badge, Chip, ListRow, StateMessage } from '../ui/Display';
import type { BadgeTone } from '../ui/Display';
import Icon from '../ui/Icon';
import { Popover } from '../ui/Overlay';
import Segmented from '../ui/Segmented';
import WorldClock from './WorldClock';
import styles from './EventsSidebar.module.css';

const RANGES: { value: TimeRange; label: string }[] = [
  { value: '24h', label: '24h' },
  { value: '48h', label: '48h' },
  { value: '7d', label: '7 days' },
];

const SHOW: { value: EventsTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'major', label: 'Major only' },
  { value: 'categories', label: 'By category' },
];

const SORTS: { key: CrisisSortKey; label: string }[] = [
  { key: 'severity', label: 'Severity' },
  { key: 'newest', label: 'Newest' },
  { key: 'country', label: 'Country' },
];

const ALERT_TONE: Record<string, BadgeTone> = { Red: 'alertRed', Orange: 'alertOrange', Green: 'alertGreen' };

// ---- Events ---------------------------------------------------------------------------------------------------------

function EventsList() {
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const eventsTab = useUiStore((s) => s.eventsTab);
  const setEventsTab = useUiStore((s) => s.setEventsTab);
  const activeCategory = useUiStore((s) => s.activeCategory);
  const setActiveCategory = useUiStore((s) => s.setActiveCategory);
  const scope = useUiStore((s) => s.scope);
  const setScope = useUiStore((s) => s.setScope);
  const timeRange = useUiStore((s) => s.timeRange);
  const setTimeRange = useUiStore((s) => s.setTimeRange);
  const reportedAtNight = useUiStore((s) => s.reportedAtNight);
  const setReportedAtNight = useUiStore((s) => s.setReportedAtNight);
  const sort = useUiStore((s) => s.eventsSort);
  const setSort = useUiStore((s) => s.setEventsSort);

  // scope and time range are server-side filters: the backend's `?scope=` / `?days=` query params, so the list matches what
  // the backend actually classified and bounded.
  const { data: crises, isLoading, isError, refetch } = useVisibleCrises(scope, timeRange);

  // The categories to offer, with how many events each has: the headline topics first (only those with events), then the
  // feed's own types present in the data. Types a topic already covers (civil unrest, election) are not repeated.
  const categories = useMemo(() => {
    const typeCounts = new Map<string, number>();
    const topicCounts = new Map<string, number>();
    for (const c of crises ?? []) {
      if (c.type) typeCounts.set(c.type, (typeCounts.get(c.type) ?? 0) + 1);
      for (const topic of topicsOf(c)) topicCounts.set(topic, (topicCounts.get(topic) ?? 0) + 1);
    }
    return [
      ...TOPICS.filter((t) => topicCounts.has(t.value)).map((t) => ({ value: t.value as string, label: t.label, count: topicCounts.get(t.value) ?? 0 })),
      ...[...typeCounts.keys()]
        .filter((type) => !TYPES_COVERED_BY_TOPICS.has(type))
        .sort()
        .map((type) => ({ value: type, label: typeLabel(type), count: typeCounts.get(type) ?? 0 })),
    ];
  }, [crises]);

  // The same filter the globe applies, so list and pins always agree. Sorting only changes the list.
  const night = useReportedAtNight(crises);
  const rows = useMemo(
    () => sortCrises(applyCrisisFilter(crises ?? [], eventsTab, activeCategory, night.ids), sort),
    [crises, eventsTab, activeCategory, night.ids, sort],
  );
  const activeFilters = (eventsTab === 'major' || (eventsTab === 'categories' && activeCategory) ? 1 : 0) + (reportedAtNight ? 1 : 0);

  // Windowed list: only the rows on screen (plus a small overscan) exist in the DOM, however many events there are.
  const listRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 40,
    overscan: 10,
  });

  function chooseShow(tab: EventsTab) {
    setEventsTab(tab);
    if (tab !== 'categories') setActiveCategory(null);
  }

  function clearFilters() {
    chooseShow('all');
    setReportedAtNight(false);
  }

  function chooseSort(key: CrisisSortKey) {
    setSort(sort.key === key ? { key, dir: sort.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: defaultDirection(key) });
  }

  return (
    <>
      <div className={styles.head}>
        <span className={styles.title}>Events</span>
        <span className={styles.count}>{rows.length.toLocaleString()}</span>
        <span className={styles.grow} />
        <Popover label="Filters" icon="settings" align="end" badge={activeFilters}>
          <div className={styles.filters}>
            <div>
              <span className={styles.groupTitle}>Show</span>
              <Segmented label="Which events to show" size="sm" block value={eventsTab} onChange={chooseShow} options={SHOW} />
              <p className={styles.hint}>Major means Severe or Critical (a score of 60 or more).</p>
              {eventsTab === 'categories' && (
                <div className={styles.chips}>
                  {categories.length === 0 && <span className={styles.hint}>No categories yet.</span>}
                  {categories.map((category) => (
                    <Chip
                      key={category.value}
                      pressed={activeCategory === category.value}
                      count={category.count}
                      onClick={() => setActiveCategory(activeCategory === category.value ? null : category.value)}
                    >
                      {category.label}
                    </Chip>
                  ))}
                </div>
              )}
            </div>
            <div>
              <span className={styles.groupTitle}>Time of day</span>
              <label className={styles.switch}>
                <input type="checkbox" role="switch" checked={reportedAtNight} onChange={(e) => setReportedAtNight(e.target.checked)} />
                <span>First reported at night (local time)</span>
              </label>
              <p className={styles.hint}>
                {reportedAtNight
                  ? night.loading
                    ? 'Working out local times…'
                    : `Between 22:00 and 05:00 at the event's own location. Only news-feed events with a city-level or better location can be judged; ${night.excluded} others are left out. This is when the report appeared, not when it happened.`
                  : 'Between 22:00 and 05:00 where the event is. This is when the report appeared, not when it happened.'}
              </p>
            </div>
            <Button size="sm" variant="quiet" disabled={activeFilters === 0} onClick={clearFilters}>
              Clear filters
            </Button>
          </div>
        </Popover>
      </div>

      <div className={styles.toolbar}>
        <Segmented
          label="Scope"
          size="sm"
          value={scope}
          onChange={setScope}
          options={[{ value: 'global', label: 'Global' }, { value: 'local', label: 'Local' }, { value: 'all', label: 'All' }]}
        />
        <Segmented label="Time range" size="sm" value={timeRange} onChange={setTimeRange} options={RANGES} />
      </div>

      <div className={styles.sortStrip} role="group" aria-label="Sort events">
        <span className={styles.sortLabel}>Sort</span>
        {SORTS.map((option) => (
          <button
            key={option.key}
            type="button"
            aria-pressed={sort.key === option.key}
            className={`${styles.sortButton} ${sort.key === option.key ? styles.sortOn : ''}`}
            onClick={() => chooseSort(option.key)}
          >
            {option.label}
            {sort.key === option.key && <Icon name="chevron-down" size={11} />}
            {sort.key === option.key && <span className={styles.srOnly}>{sort.dir === 'asc' ? ', ascending' : ', descending'}</span>}
          </button>
        ))}
      </div>

      {scope === 'local' && <p className={styles.note}>Local reports: severity scores are unreliable for this content and are not shown at face value.</p>}

      {isLoading && <StateMessage kind="loading" title="Loading events…" />}
      {isError && !crises && <StateMessage kind="error" title="Couldn't load events" hint="The server did not answer." actionLabel="Try again" onAction={() => refetch()} />}
      {!isLoading && crises && rows.length === 0 && (
        <StateMessage kind="empty" title="No events match" hint={activeFilters ? 'Try clearing a filter.' : 'Try a wider time range.'} />
      )}

      <div className={styles.list} ref={listRef}>
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((row) => {
            const crisis = rows[row.index];
            const isLocal = crisis.scope === 'local';
            return (
              <ListRow
                key={crisis.id}
                data-index={row.index}
                ref={virtualizer.measureElement}
                dense
                title={crisis.title}
                selected={pinnedSelection?.kind === 'event' && pinnedSelection.crisis.id === crisis.id}
                style={{ position: 'absolute', top: 0, left: 0, transform: `translateY(${row.start}px)` }}
                onClick={() => selectCrisis(crisis)}
                detail={
                  <>
                    {isLocal ? <Badge compact>Unreliable</Badge> : <Badge compact tone={severityTone(crisis.severity)}>{labelForSeverity(crisis.severity)}</Badge>}
                    <span className={styles.metaText}>{crisis.country}</span>
                    <span className={styles.metaAge}>{shortAge(parseUtc(crisis.date))}</span>
                  </>
                }
              />
            );
          })}
        </div>
      </div>
    </>
  );
}

// ---- Weather ---------------------------------------------------------------------------------------------------------

const ALERT_RANK: Record<string, number> = { Red: 0, Orange: 1, Green: 2 };

// Most urgent first (GDACS alert level), then cyclones before the rest, then most recently updated.
function compareHazards(a: Storm, b: Storm): number {
  const alert = (ALERT_RANK[a.alert_level ?? ''] ?? 3) - (ALERT_RANK[b.alert_level ?? ''] ?? 3);
  if (alert) return alert;
  const type = (a.event_type === 'TC' ? 0 : 1) - (b.event_type === 'TC' ? 0 : 1);
  if (type) return type;
  return (b.date_modified ?? '').localeCompare(a.date_modified ?? '');
}

const HAZARD_SHOW: { value: EventsTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'major', label: 'Major (Orange, Red)' },
  { value: 'categories', label: 'By type' },
];

// Weather mode's list: the same active hazards the globe shows, with the same filter as the globe, so what is listed is
// what is drawn.
function WeatherList() {
  const selectHazard = useUiStore((s) => s.selectHazard);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const tab = useUiStore((s) => s.weatherTab);
  const setTab = useUiStore((s) => s.setWeatherTab);
  const category = useUiStore((s) => s.weatherCategory);
  const setCategory = useUiStore((s) => s.setWeatherCategory);
  const { data, isLoading, isError, refetch } = useStormsQuery(true);

  const hazards = useMemo(() => applyHazardFilter(data?.storms ?? [], tab, category).sort(compareHazards), [data, tab, category]);

  function chooseShow(next: EventsTab) {
    setTab(next);
    if (next !== 'categories') setCategory(null);
  }

  return (
    <>
      <div className={styles.head}>
        <span className={styles.title}>Weather</span>
        {data && <span className={styles.count}>{hazards.length}</span>}
      </div>

      <div className={styles.toolbar}>
        <Segmented label="Which hazards to show" size="sm" block value={tab} onChange={chooseShow} options={HAZARD_SHOW} />
      </div>
      {tab === 'categories' && (
        <div className={styles.chips}>
          {HAZARD_TYPES.map((type) => (
            <Chip key={type.code} pressed={category === type.code} onClick={() => setCategory(category === type.code ? null : type.code)}>
              {type.label}
            </Chip>
          ))}
        </div>
      )}

      {isLoading && <StateMessage kind="loading" title="Loading active hazards…" />}
      {isError && !data && <StateMessage kind="error" title="Live hazard data isn't available" actionLabel="Try again" onAction={() => refetch()} />}
      {data && hazards.length === 0 && <StateMessage kind="empty" title="No active weather hazards to show" />}
      <div className={styles.list}>
        {hazards.map((hazard) => {
          const active =
            pinnedSelection?.kind === 'hazard' && pinnedSelection.hazard.id === hazard.id && pinnedSelection.hazard.event_type === hazard.event_type;
          return (
            <ListRow
              key={`${hazard.event_type}-${hazard.id}`}
              dense
              title={hazard.name ?? hazard.hazard ?? 'Weather event'}
              selected={active}
              onClick={() => selectHazard(hazard)}
              leading={<Icon name={hazardIconName(hazard.event_type)} size={16} />}
              detail={
                <>
                  <Badge compact tone={ALERT_TONE[hazard.alert_level ?? ''] ?? 'neutral'}>{hazard.alert_level ? `${hazard.alert_level} alert` : 'No alert level'}</Badge>
                  {hazard.country && <span className={styles.metaText}>{hazard.country}</span>}
                  <span className={styles.metaAge}>{shortAge(parseUtc(hazard.date_modified))}</span>
                </>
              }
            />
          );
        })}
      </div>
    </>
  );
}

export default function EventsSidebar({ docked }: { docked: boolean }) {
  const leftOpen = useUiStore((s) => s.leftOpen);
  const activeMode = useUiStore((s) => s.activeMode);
  const [full, setFull] = useState(false);

  return (
    <aside
      data-ui-hover-surface
      className={`${styles.sidebar} ${docked ? styles.docked : styles.overlay} ${leftOpen ? styles.open : styles.closed} ${full ? styles.full : ''}`}
    >
      <SheetHandle full={full} onToggle={() => setFull(!full)} onClose={() => useUiStore.getState().setLeftOpen(false)} />
      {activeMode === 'weather' ? <WeatherList /> : activeMode === 'timezone' ? <WorldClock /> : <EventsList />}
    </aside>
  );
}
