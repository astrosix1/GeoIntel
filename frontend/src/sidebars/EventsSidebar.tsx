import { useMemo } from 'react';
import { useUiStore } from '../state/uiStore';
import type { EventsTab } from '../state/uiStore';
import { useCrisesQuery } from '../state/queries';
import { colorForSeverity } from '../globe/severity';
import styles from './EventsSidebar.module.css';

const TABS: { value: EventsTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'major', label: 'Major' },
  { value: 'categories', label: 'Categories' },
];

export default function EventsSidebar() {
  const leftOpen = useUiStore((s) => s.leftOpen);
  const setLeftPanelHovered = useUiStore((s) => s.setLeftPanelHovered);
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const eventsTab = useUiStore((s) => s.eventsTab);
  const setEventsTab = useUiStore((s) => s.setEventsTab);
  const activeCategory = useUiStore((s) => s.activeCategory);
  const setActiveCategory = useUiStore((s) => s.setActiveCategory);
  const scope = useUiStore((s) => s.scope);
  const setScope = useUiStore((s) => s.setScope);

  // scope is a server-side filter (10.4) — the backend's `?scope=` query
  // param, not a client-side array filter — so the list matches what the
  // backend actually classified.
  const { data: crises, isLoading, isError } = useCrisesQuery(scope);

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
      onMouseEnter={() => setLeftPanelHovered(true)}
      onMouseLeave={() => setLeftPanelHovered(false)}
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
      <div className={styles.list}>
        {filteredCrises.map((crisis) => {
          const isLocal = crisis.scope === 'local';
          return (
            <button
              key={crisis.id}
              type="button"
              className={`${styles.item} ${pinnedSelection?.kind === 'event' && pinnedSelection.crisis.id === crisis.id ? styles.itemActive : ''}`}
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
    </aside>
  );
}
