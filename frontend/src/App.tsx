import Globe from './globe/Globe';
import ModeSwitcher from './globe/ModeSwitcher';
import EventsSidebar from './sidebars/EventsSidebar';
import AnalysisSidebar from './sidebars/AnalysisSidebar';
import EdgeTab from './sidebars/EdgeTab';
import SolarSystem from './background/SolarSystem';
import Logo from './Logo';
import AccountChip from './components/AccountChip';
import './App.css';

function App() {
  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <SolarSystem />
      <div style={{ position: 'absolute', inset: 0, zIndex: 1 }}>
        <Globe />
      </div>
      <Logo />
      <AccountChip />
      <ModeSwitcher />
      <EventsSidebar />
      <AnalysisSidebar />
      <EdgeTab side="left" />
      <EdgeTab side="right" />
    </div>
  );
}

export default App;
