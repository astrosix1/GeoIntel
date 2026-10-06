import { lazy, Suspense } from 'react';
import Globe from './globe/Globe';
import ModeSwitcher from './globe/ModeSwitcher';
import LayerControl from './globe/LayerControl';
import WeatherLegend from './globe/WeatherLegend';
import TimeBar from './globe/TimeBar';
import MapLegend from './globe/MapLegend';
import EventsSidebar from './sidebars/EventsSidebar';
import AnalysisSidebar from './sidebars/AnalysisSidebar';
import EdgeTab from './sidebars/EdgeTab';
import Logo from './Logo';
import AccountChip from './components/AccountChip';
import Dashboard from './components/Dashboard';
import { useShareLink } from './state/useShareLink';

// Decorative only — loaded after the globe so it never delays first paint.
const SolarSystem = lazy(() => import('./background/SolarSystem'));

function App() {
  useShareLink();
  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <Suspense fallback={null}>
        <SolarSystem />
      </Suspense>
      <div style={{ position: 'absolute', inset: 0, zIndex: 1 }}>
        <Globe />
      </div>
      <Logo />
      <AccountChip />
      <Dashboard />
      <ModeSwitcher />
      <WeatherLegend />
      <TimeBar />
      <MapLegend />
      <LayerControl />
      <EventsSidebar />
      <AnalysisSidebar />
      <EdgeTab side="left" />
      <EdgeTab side="right" />
    </div>
  );
}

export default App;
