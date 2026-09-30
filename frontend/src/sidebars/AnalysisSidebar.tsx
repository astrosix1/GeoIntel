import { useUiStore } from '../state/uiStore';
import EventAnalysis from './analysis/EventAnalysis';
import CountryAnalysis from './analysis/CountryAnalysis';
import styles from './AnalysisSidebar.module.css';

export default function AnalysisSidebar() {
  const rightOpen = useUiStore((s) => s.rightOpen);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const setRightPanelHovered = useUiStore((s) => s.setRightPanelHovered);

  // Visibility is hover-driven only (10.2) — pinnedSelection controls WHAT
  // is shown, never WHETHER the panel is shown.
  const isOpen = rightOpen;

  return (
    <aside
      data-ui-hover-surface
      className={`${styles.sidebar} ${isOpen ? styles.open : ''}`}
      onMouseEnter={() => setRightPanelHovered(true)}
      onMouseLeave={() => setRightPanelHovered(false)}
    >
      <div className={styles.header}>Analysis</div>
      <div className={styles.body}>
        {pinnedSelection?.kind === 'event' && <EventAnalysis crisis={pinnedSelection.crisis} />}
        {pinnedSelection?.kind === 'country' && <CountryAnalysis countryCode={pinnedSelection.countryCode} />}
        {!pinnedSelection && (
          <div className={styles.placeholder}>
            Click a crisis pin or a country on the globe, or an item in Events, to see its analysis here.
          </div>
        )}
      </div>
    </aside>
  );
}
