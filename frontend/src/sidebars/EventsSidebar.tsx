import { useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useUiStore } from '../state/uiStore';
import type { EventsTab, TimeRange } from '../state/uiStore';
import { useStormsQuery, useVisibleCrises } from '../state/queries';
import { colorForSeverity } from '../globe/severity';
import { ALERT_COLORS, HAZARD_TYPES, hazardIcon } from '../globe/hazards';
import { applyCrisisFilter, applyHazardFilter } from '../lib/filters';
import type { Storm } from '../api/types';
import WorldClock from './WorldClock';
import styles from './EventsSidebar.module.css';

const TABS: { value: EventsTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'major', label: 'Major' },
  { value: 'categories', label: 'Categories' },
];

const RANGES: { value: TimeRange; label: string }[] = [
  { value: '24h', label: '24h' },
  { value: '48h', label: '48h' },
  { value: '7d', label: '7 days' },
];

// The All / Major / Categories row, shared by Events and Weather mode so the
// two look and behave the same.
function FilterTabs({ value, onChange }: { value: EventsTab; onChange: (tab: EventsTab) => void }) {
  return (
    <div className={styles.tabRow}>
      {TABS.map((tab) => (
        <button
          key={tab.value}
          type="button"
          className={`${styles.tabButton} ${value === tab.value ? styles.tabActive : ''}`}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function CategoryChips({
  items,
  active,
  onToggle,
  emptyText,
}: {
  items: { value: string; label: string }[];
  active: string | null;
  onToggle: (value: string) => void;
  emptyText: string;
}) {
  return (
    <div className={styles.chipRow}>
      {items.length === 0 && <span className={styles.chipEmpty}>{emptyText}</span>}
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          aria-pressed={active === item.value}
          className={`${styles.chip} ${active === item.value ? styles.chipActive : ''}`}
          onClick={() => onToggle(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

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

  // scope and time range are server-side filters (10.4) — the backend's
  // `?scope=` / `?days=` query params, not client-side array filters — so
  // the list matches what the backend actually classified and bounded.
  const { data: crises, isLoading, isError } = useVisibleCrises(scope, timeRange);

  // Real distinct `type` values present in the fetched data, not a
  // hardcoded list (10.1) — whatever categories actually show up.
  const categories = useMemo(() => {
    const distinct = new Set((crises ?? []).map((c) => c.type).filter(Boolean));
    return Array.from(distinct)
      .sort()
      .map((value) => ({ value, label: value }));
  }, [crises]);

  // The same filter the globe applies, so list and pins always agree.
  const filteredCrises = useMemo(
    () => applyCrisisFilter(crises ?? [], eventsTab, activeCategory),
    [crises, eventsTab, activeCategory],
  );

  // Windowed list: only the rows on screen (plus a small overscan) exist in
  // the DOM, however many events the list holds. Rows wrap to a variable
  // height, so each is measured after render.
  const listRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: filteredCrises.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 62,
    overscan: 8,
  });

  function handleTabClick(tab: EventsTab) {
    setEventsTab(tab);
    if (tab !== 'categories') setActiveCategory(null);
  }

  return (
    <>
      <div className={styles.header}>Events{filteredCrises ? ` (${filteredCrises.length})` : ''}</div>

      <div className={styles.scopeToggle}>
        <button
          type="button"
          className={`${styles.scopeOption} ${scope === 'global' ? styles.scopeActive : ''}`}
          onClick={() => setScope('global')}
        >
          Global
        </button>
        <button
          type="button"
          className={`${styles.scopeOption} ${scope === 'local' ? styles.scopeActive : ''}`}
          onClick={() => setScope('local')}
        >
          Local
        </button>
      </div>

      <div className={styles.scopeToggle}>
        {RANGES.map((range) => (
          <button
            key={range.value}
            type="button"
            className={`${styles.scopeOption} ${timeRange === range.value ? styles.scopeActive : ''}`}
            onClick={() => setTimeRange(range.value)}
          >
            {range.label}
          </button>
        ))}
      </div>

      <FilterTabs value={eventsTab} onChange={handleTabClick} />

      {eventsTab === 'categories' && (
        <CategoryChips
          items={categories}
          active={activeCategory}
          onToggle={(value) => setActiveCategory(activeCategory === value ? null : value)}
          emptyText="No categories yet"
        />
      )}

      {scope === 'local' && (
        <div className={styles.scopeCaveat}>
          Local reports — severity scores are unreliable for this content and shown muted below.
        </div>
      )}

      {isLoading && <div className={styles.status}>Loading crises...</div>}
      {isError && <div className={styles.status}>Failed to load crises.</div>}
      <div className={styles.list} ref={listRef}>
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((row) => {
            const crisis = filteredCrises[row.index];
            const isLocal = crisis.scope === 'local';
            return (
              <button
                key={crisis.id}
                data-index={row.index}
                ref={virtualizer.measureElement}
                type="button"
                className={`${styles.item} ${pinnedSelection?.kind === 'event' && pinnedSelection.crisis.id === crisis.id ? styles.itemActive : ''}`}
                style={{ position: 'absolute', top: 0, left: 0, transform: `translateY(${row.start}px)` }}
                onClick={() => selectCrisis(crisis)}
              >
                <div className={styles.itemTitle}>{crisis.title}</div>
                <div className={styles.itemMeta}>
                  <span
                    className={styles.severityDot}
                    style={{ backgroundColor: isLocal ? 'rgba(230, 233, 239, 0.35)' : colorForSeverity(crisis.severity) }}
                  />
                  <span>{crisis.country}</span>
                  <span>&middot;</span>
                  <span>{isLocal ? 'severity unreliable' : `severity ${crisis.severity}`}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

const ALERT_RANK: Record<string, number> = { Red: 0, Orange: 1, Green: 2 };

// Most urgent first (GDACS alert level), then cyclones before the rest, then
// most recently updated.
function compareHazards(a: Storm, b: Storm): number {
  const alert = (ALERT_RANK[a.alert_level ?? ''] ?? 3) - (ALERT_RANK[b.alert_level ?? ''] ?? 3);
  if (alert) return alert;
  const type = (a.event_type === 'TC' ? 0 : 1) - (b.event_type === 'TC' ? 0 : 1);
  if (type) return type;
  return (b.date_modified ?? '').localeCompare(a.date_modified ?? '');
}

const HAZARD_CATEGORIES = HAZARD_TYPES.map((t) => ({ value: t.code, label: `${t.icon} ${t.label}` }));

// Weather mode's list: the same active hazards the globe shows, with the same
// All / Major / Categories row as Events mode. The filter is shared with the
// globe, so what's listed is what's drawn.
function WeatherList() {
  const selectHazard = useUiStore((s) => s.selectHazard);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const tab = useUiStore((s) => s.weatherTab);
  const setTab = useUiStore((s) => s.setWeatherTab);
  const category = useUiStore((s) => s.weatherCategory);
  const setCategory = useUiStore((s) => s.setWeatherCategory);
  const { data, isLoading, isError, refetch } = useStormsQuery(true);

  const hazards = useMemo(
    () => applyHazardFilter(data?.storms ?? [], tab, category).sort(compareHazards),
    [data, tab, category],
  );

  function handleTabClick(next: EventsTab) {
    setTab(next);
    if (next !== 'categories') setCategory(null);
  }

  return (
    <>
      <div className={styles.header}>Weather{data ? ` (${hazards.length})` : ''}</div>

      <FilterTabs value={tab} onChange={handleTabClick} />

      {tab === 'categories' && (
        <CategoryChips
          items={HAZARD_CATEGORIES}
          active={category}
          onToggle={(value) => setCategory(category === value ? null : value)}
          emptyText="No categories yet"
        />
      )}
      {tab === 'major' && <div className={styles.scopeCaveat}>Major = GDACS Orange and Red alerts.</div>}

      {isLoading && <div className={styles.status}>Loading active events...</div>}
      {isError && (
        <div className={styles.status}>
          Live hazard data isn&apos;t available right now.{' '}
          <button type="button" className={styles.chip} onClick={() => refetch()}>
            Try again
          </button>
        </div>
      )}
      {data && hazards.length === 0 && <div className={styles.status}>No active weather hazards to show.</div>}
      <div className={styles.list}>
        {hazards.map((hazard) => {
          const active =
            pinnedSelection?.kind === 'hazard' &&
            pinnedSelection.hazard.id === hazard.id &&
            pinnedSelection.hazard.event_type === hazard.event_type;
          return (
            <button
              key={`${hazard.event_type}-${hazard.id}`}
              type="button"
              className={`${styles.item} ${active ? styles.itemActive : ''}`}
              style={{ position: 'static' }}
              onClick={() => selectHazard(hazard)}
            >
              <div className={styles.itemTitle}>
                {hazardIcon(hazard.event_type)} {hazard.name ?? hazard.hazard ?? 'Weather event'}
              </div>
              <div className={styles.itemMeta}>
                <span
                  className={styles.severityDot}
                  style={{ backgroundColor: ALERT_COLORS[hazard.alert_level ?? 'Unknown'] ?? ALERT_COLORS.Unknown }}
                />
                <span>{hazard.alert_level ?? 'Unknown'} alert</span>
                {hazard.country && (
                  <>
                    <span>&middot;</span>
                    <span>{hazard.country}</span>
                  </>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </>
  );
}

export default function EventsSidebar() {
  const leftOpen = useUiStore((s) => s.leftOpen);
  const activeMode = useUiStore((s) => s.activeMode);

  return (
    <aside
      data-ui-hover-surface
      className={`${styles.sidebar} ${leftOpen ? styles.open : ''}`}
    >
      {activeMode === 'weather' ? <WeatherList /> : activeMode === 'timezone' ? <WorldClock /> : <EventsList />}
    </aside>
  );
}
