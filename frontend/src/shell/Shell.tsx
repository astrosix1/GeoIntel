import { lazy, Suspense, useEffect } from 'react';
import Globe from '../globe/Globe';
import TimeBar from '../globe/TimeBar';
import AnalysisSidebar from '../sidebars/AnalysisSidebar';
import EdgeTab from '../sidebars/EdgeTab';
import EventsSidebar from '../sidebars/EventsSidebar';
import Dashboard from '../components/Dashboard';
import { useSettings, usePanelsDocked } from '../state/settings';
import { useUiStore } from '../state/uiStore';
import ContextStrip from './ContextStrip';
import StatusBar from './StatusBar';
import TopBar from './TopBar';
import styles from './Shell.module.css';

// Decorative only, loaded after the map so it never delays first paint. It can be switched off in Settings.
const SolarSystem = lazy(() => import('../background/SolarSystem'));

// The page frame (docs/ui-redesign-plan.md): a top bar, a strip of mode controls, the working area and a status bar.
// With the panels docked they are columns beside the map, which is sized to the space left; with "Overlay on hover" the
// map is the whole working area and the panels slide over it, as before.
export default function Shell() {
  const docked = usePanelsDocked();
  const starfield = useSettings((s) => s.starfield);
  const pinned = useUiStore((s) => s.pinnedSelection);
  const setLeftOpen = useUiStore((s) => s.setLeftOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);

  // Docked: the events panel is there from the start, and the analysis panel opens when something is selected.
  useEffect(() => {
    if (docked) setLeftOpen(true);
  }, [docked, setLeftOpen]);
  useEffect(() => {
    if (docked && pinned) setRightOpen(true);
  }, [docked, pinned, setRightOpen]);

  // Phones: panels are bottom sheets, so picking something swaps the list sheet for its details.
  useEffect(() => {
    if (!pinned || !window.matchMedia('(max-width: 768px)').matches) return;
    setLeftOpen(false);
    setRightOpen(true);
  }, [pinned, setLeftOpen, setRightOpen]);

  return (
    <>
      {starfield && (
        <Suspense fallback={null}>
          <SolarSystem />
        </Suspense>
      )}
      <div className={styles.shell}>
        <TopBar />
        <ContextStrip />
        <div className={docked ? styles.body : styles.bodyOverlay}>
          <EventsSidebar docked={docked} />
          <div className={styles.map}>
            <div className={styles.globe}>
              <Globe />
            </div>
            <TimeBar />
            <EdgeTab side="left" docked={docked} />
            <EdgeTab side="right" docked={docked} />
          </div>
          <AnalysisSidebar docked={docked} />
        </div>
        <StatusBar />
      </div>
      <Dashboard />
    </>
  );
}
