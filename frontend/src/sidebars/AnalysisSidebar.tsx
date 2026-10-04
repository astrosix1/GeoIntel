import { useUiStore } from '../state/uiStore';
import EventAnalysis from './analysis/EventAnalysis';
import CountryAnalysis from './analysis/CountryAnalysis';
import HazardAnalysis from './analysis/HazardAnalysis';
import PointForecast from './analysis/PointForecast';
import styles from './AnalysisSidebar.module.css';

export default function AnalysisSidebar() {
  const rightOpen = useUiStore((s) => s.rightOpen);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);

  // Visibility is controlled by the right EdgeTab (open on hover, close via
  // its × button) — pinnedSelection controls WHAT is shown, never WHETHER
  // the panel is shown.
  const isOpen = rightOpen;

  return (
    <aside
      data-ui-hover-surface
      className={`${styles.sidebar} ${isOpen ? styles.open : ''}`}
    >
      <div className={styles.header}>Analysis</div>
      <div className={styles.body}>
        {pinnedSelection?.kind === 'event' && (
          <EventAnalysis key={pinnedSelection.crisis.id} crisis={pinnedSelection.crisis} />
        )}
        {pinnedSelection?.kind === 'country' && <CountryAnalysis countryCode={pinnedSelection.countryCode} />}
        {pinnedSelection?.kind === 'hazard' && (
          <HazardAnalysis key={`${pinnedSelection.hazard.event_type}-${pinnedSelection.hazard.id}`} hazard={pinnedSelection.hazard} />
        )}
        {pinnedSelection?.kind === 'point' && (
          <PointForecast
            key={`${pinnedSelection.lat}:${pinnedSelection.lon}`}
            lat={pinnedSelection.lat}
            lon={pinnedSelection.lon}
            label={pinnedSelection.label}
          />
        )}
        {!pinnedSelection && (
          <div className={styles.placeholder}>
            Click a crisis pin or a country on the globe, or an item in Events, to see its analysis here.
          </div>
        )}
      </div>
    </aside>
  );
}
