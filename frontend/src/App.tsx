import Globe from './globe/Globe';
import ModeSwitcher from './globe/ModeSwitcher';
import EventsSidebar from './sidebars/EventsSidebar';
import AnalysisSidebar from './sidebars/AnalysisSidebar';
import EdgeTab from './sidebars/EdgeTab';
import { useHoverZone } from './sidebars/useHoverZone';
import SolarSystem from './background/SolarSystem';
import Logo from './Logo';
import './App.css';

function App() {
  useHoverZone();

  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <SolarSystem />
      <div style={{ position: 'absolute', inset: 0, zIndex: 1 }}>
        <Globe />
      </div>
      <Logo />
      <ModeSwitcher />
      <EventsSidebar />
      <AnalysisSidebar />
      <EdgeTab side="left" />
      <EdgeTab side="right" />
    </div>
  );
}

export default App;
