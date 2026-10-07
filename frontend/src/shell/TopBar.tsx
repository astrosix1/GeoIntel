import PremiumGate from '../components/PremiumGate';
import { isDemoPremium, isSignInConfigured, signIn, signOut } from '../auth/session';
import { useAlertsQuery, useEntitlements } from '../state/queries';
import { useDrawStore } from '../state/drawStore';
import { useUiStore } from '../state/uiStore';
import type { GlobeMode } from '../state/uiStore';
import Button from '../ui/Button';
import { Badge } from '../ui/Display';
import Icon from '../ui/Icon';
import Segmented from '../ui/Segmented';
import LayersMenu from './LayersMenu';
import SettingsMenu from './SettingsMenu';
import styles from './Bar.module.css';

const MODES: { value: GlobeMode; label: string }[] = [
  { value: 'events', label: 'Events' },
  { value: 'weather', label: 'Weather' },
  { value: 'timezone', label: 'Time Zone' },
];

// One bar for what used to be six floating groups: the wordmark, the three modes, the map layers, the settings, the
// dashboard and the account. Switching modes never closes a panel or clears the selection (see uiStore.setActiveMode).
// Opens or hides the drawing tools. The drawing itself stays on the map when the tools are hidden.
function DrawButton() {
  const open = useDrawStore((s) => s.open);
  const setOpen = useDrawStore((s) => s.setOpen);
  return (
    <span className={styles.drawTop}>
      <Button icon="pencil" variant={open ? 'primary' : 'default'} aria-pressed={open} onClick={() => setOpen(!open)}>
        Draw
      </Button>
    </span>
  );
}

export default function TopBar() {
  const activeMode = useUiStore((s) => s.activeMode);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const setDashboardOpen = useUiStore((s) => s.setDashboardOpen);
  const setDashboardTab = useUiStore((s) => s.setDashboardTab);
  const { signedIn, premium, loading } = useEntitlements();
  const unread = useAlertsQuery().data?.unread ?? 0;

  // Locked for anyone who isn't premium (the gate shows the sign-in or upgrade prompt). Always drawn, even while the plan is
  // loading or the backend is down, so the button is never missing.
  const dashboard = (
    <Button
      icon="user"
      onClick={() => {
        if (premium && unread > 0) setDashboardTab('alerts');
        setDashboardOpen(true);
      }}
    >
      <span className={styles.hideSmall}>Dashboard</span>
      {premium && unread > 0 && <span className={styles.unread}><Badge tone="accent">{unread}</Badge></span>}
    </Button>
  );

  // Sign in for visitors, Sign out for free members. Premium members sign out from inside their dashboard.
  let account = null;
  if (!loading && !premium) {
    if (!signedIn && isSignInConfigured()) account = <Button variant="quiet" onClick={signIn}>Sign in</Button>;
    else if (signedIn) account = <Button variant="quiet" onClick={signOut}>Sign out</Button>;
  }

  return (
    <header className={styles.top}>
      <div className={styles.brand}>
        <Icon name="globe" size={18} />
        <span className={styles.hideSmall}>GeoIntel</span>
        {premium && <Badge tone="accent">{isDemoPremium() ? 'Premium (demo)' : 'Premium'}</Badge>}
      </div>
      <Segmented label="Mode" value={activeMode} onChange={setActiveMode} options={MODES} />
      <div className={styles.spacer} />
      <div className={styles.group}>
        <DrawButton />
        <LayersMenu />
        <SettingsMenu />
        {premium ? dashboard : <PremiumGate feature="Dashboard" account>{dashboard}</PremiumGate>}
        {account}
      </div>
    </header>
  );
}
