import PremiumGate from '../components/PremiumGate';
import watch from '../components/Watchlist.module.css';
import { useAlertsQuery, useEntitlements } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import type { GlobeMode } from '../state/uiStore';
import styles from './ModeSwitcher.module.css';

// Persistent top menu (step 5 of the rewrite plan): the three globe modes,
// then the Dashboard button for signed-in users. Switching modes never closes
// a sidebar or clears the pinned Analysis selection (see uiStore.setActiveMode)
// — it only changes what Globe.tsx renders on the map itself.
const MODES: { value: GlobeMode; label: string }[] = [
  { value: 'events', label: 'Events' },
  { value: 'weather', label: 'Weather' },
  { value: 'timezone', label: 'Time Zone' },
];

export default function ModeSwitcher() {
  const activeMode = useUiStore((s) => s.activeMode);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const setDashboardOpen = useUiStore((s) => s.setDashboardOpen);
  const setDashboardTab = useUiStore((s) => s.setDashboardTab);
  const { premium } = useEntitlements();
  const unread = useAlertsQuery().data?.unread ?? 0;

  // Locked for anyone who isn't premium (anonymous visitors get the Sign in
  // prompt, free members the Upgrade one), like every premium control. Always
  // drawn, even while the plan is still loading or the backend is down, so the
  // button is never missing; members just see it unlock once their plan arrives.
  const dashboardButton = (
    <button
      type="button"
      className={`${styles.option} ${styles.dashboard}`}
      onClick={() => {
        // New alerts waiting: go straight to them.
        if (premium && unread > 0) setDashboardTab('alerts');
        setDashboardOpen(true);
      }}
    >
      Dashboard
      {premium && unread > 0 && <span className={watch.badge}>{unread}</span>}
    </button>
  );

  return (
    <div className={styles.switcher} data-ui-hover-surface>
      {MODES.map((mode) => (
        <button
          key={mode.value}
          type="button"
          className={`${styles.option} ${activeMode === mode.value ? styles.optionActive : ''}`}
          onClick={() => setActiveMode(mode.value)}
        >
          {mode.label}
        </button>
      ))}
      {premium ? dashboardButton : <PremiumGate feature="Dashboard">{dashboardButton}</PremiumGate>}
    </div>
  );
}
