import { lazy, Suspense, useEffect } from 'react';
import Globe from '../globe/Globe';
import DrawToolbar from '../globe/draw/DrawToolbar';
import PresentExit from '../globe/draw/PresentExit';
import { handleFullscreenChange, stopPresenting } from '../globe/draw/present';
import ForecastBar from '../globe/ForecastBar';
import RadarBar from '../globe/RadarBar';
import WeatherFieldLegend from '../globe/WeatherFieldLegend';
import TimeBar from '../globe/TimeBar';
import AnalysisSidebar from '../sidebars/AnalysisSidebar';
import EdgeTab from '../sidebars/EdgeTab';
import EventsSidebar from '../sidebars/EventsSidebar';
import Dashboard from '../components/Dashboard';
import CascadeWorkspace from '../components/CascadeWorkspace';
import { useDrawStore } from '../state/drawStore';
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
  const presenting = useDrawStore((s) => s.presenting);

  // Docked: the events panel is there from the start, and the analysis panel opens when something is selected.
  useEffect(() => {
    if (docked) setLeftOpen(true);
  }, [docked, setLeftOpen]);
  useEffect(() => {
    if (docked && pinned) setRightOpen(true);
  }, [docked, pinned, setRightOpen]);

  // Presentation mode: a class on the page lets the map's own controls be hidden too, and Escape leaves it.
  useEffect(() => {
    document.documentElement.classList.toggle('presenting', presenting);
    if (!presenting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') stopPresenting();
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, [presenting]);

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
      <div className={`${styles.shell} ${presenting ? styles.presenting : ''}`}>
        <TopBar />
        <ContextStrip />
        <div className={docked ? styles.body : styles.bodyOverlay}>
          <EventsSidebar docked={docked} />
          <div className={styles.map}>
            <div className={styles.globe}>
              <Globe />
            </div>
            <TimeBar />
            <ForecastBar />
            <RadarBar />
            <WeatherFieldLegend />
            <DrawToolbar />
            <PresentExit />
            <EdgeTab side="left" docked={docked} />
            <EdgeTab side="right" docked={docked} />
          </div>
          <AnalysisSidebar docked={docked} />
        </div>
        <StatusBar />
      </div>
      <Dashboard />
      <CascadeWorkspace />
    </>
  );
}
