import { lazy, Suspense } from 'react';
import Globe from './globe/Globe';
import ModeSwitcher from './globe/ModeSwitcher';
import LayerControl from './globe/LayerControl';
import WeatherLegend from './globe/WeatherLegend';
import EventsSidebar from './sidebars/EventsSidebar';
import AnalysisSidebar from './sidebars/AnalysisSidebar';
import EdgeTab from './sidebars/EdgeTab';
import Logo from './Logo';
import AccountChip from './components/AccountChip';
import Dashboard from './components/Dashboard';
import './App.css';

// Decorative only — loaded after the globe so it never delays first paint.
const SolarSystem = lazy(() => import('./background/SolarSystem'));

function App() {
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
      <LayerControl />
      <EventsSidebar />
      <AnalysisSidebar />
      <EdgeTab side="left" />
      <EdgeTab side="right" />
    </div>
  );
}

export default App;
