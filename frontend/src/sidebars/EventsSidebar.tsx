import { useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useUiStore } from '../state/uiStore';
import type { EventsTab, TimeRange } from '../state/uiStore';
import { useVisibleCrises } from '../state/queries';
import { colorForSeverity } from '../globe/severity';
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

export default function EventsSidebar() {
  const leftOpen = useUiStore((s) => s.leftOpen);
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

  const isOpen = leftOpen;

  // Real distinct `type` values present in the fetched data, not a
  // hardcoded list (10.1) — whatever categories actually show up.
  const categories = useMemo(() => {
    const distinct = new Set((crises ?? []).map((c) => c.type).filter(Boolean));
    return Array.from(distinct).sort();
  }, [crises]);

  const filteredCrises = useMemo(() => {
    const list = crises ?? [];
    if (eventsTab === 'major') return list.filter((c) => c.severity >= 70);
    if (eventsTab === 'categories' && activeCategory) {
      return list.filter((c) => c.type === activeCategory);
    }
    return list;
  }, [crises, eventsTab, activeCategory]);

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

  function handleCategoryClick(category: string) {
    setActiveCategory(activeCategory === category ? null : category);
  }

  return (
    <aside
      data-ui-hover-surface
      className={`${styles.sidebar} ${isOpen ? styles.open : ''}`}
    >
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

      <div className={styles.tabRow}>
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={`${styles.tabButton} ${eventsTab === tab.value ? styles.tabActive : ''}`}
            onClick={() => handleTabClick(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {eventsTab === 'categories' && (
        <div className={styles.chipRow}>
          {categories.length === 0 && <span className={styles.chipEmpty}>No categories yet</span>}
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              className={`${styles.chip} ${activeCategory === category ? styles.chipActive : ''}`}
              onClick={() => handleCategoryClick(category)}
            >
              {category}
            </button>
          ))}
        </div>
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
    </aside>
  );
}
