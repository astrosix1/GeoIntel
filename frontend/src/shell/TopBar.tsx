import { isDemoPremium, isSignInConfigured, signIn } from '../auth/session';
import { useAlertsQuery, useEntitlements } from '../state/queries';
import { useDrawStore } from '../state/drawStore';
import { useUiStore } from '../state/uiStore';
import type { GlobeMode } from '../state/uiStore';
import Button from '../ui/Button';
import { Badge } from '../ui/Display';
import Icon from '../ui/Icon';
import { Popover } from '../ui/Overlay';
import Segmented from '../ui/Segmented';
import LayersMenu from './LayersMenu';
import styles from './Bar.module.css';

const MODES: { value: GlobeMode; label: string }[] = [
  { value: 'events', label: 'Events' },
  { value: 'weather', label: 'Weather' },
  { value: 'timezone', label: 'Time Zone' },
];

// On phones the three modes sit in a menu (the hamburger) to leave room for Draw, Layers and the Dashboard in the bar.
function ModeMenu() {
  const activeMode = useUiStore((s) => s.activeMode);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  return (
    <div className={styles.modesPhone}>
      <Popover label={`Menu: ${MODES.find((m) => m.value === activeMode)?.label ?? ''}`} icon="menu" align="start">
        {(close) => (
          <div className={styles.modeList} role="group" aria-label="Mode">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                aria-pressed={m.value === activeMode}
                className={`${styles.modeItem} ${m.value === activeMode ? styles.modeItemActive : ''}`}
                onClick={() => {
                  setActiveMode(m.value);
                  close();
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
      </Popover>
    </div>
  );
}

// One bar for what used to be six floating groups: the wordmark, the three modes, the map layers, the settings, the
// dashboard and the account. Switching modes never closes a panel or clears the selection (see uiStore.setActiveMode).
// Opens or hides the drawing tools. The drawing itself stays on the map when the tools are hidden.
function DrawButton() {
  const open = useDrawStore((s) => s.open);
  const setOpen = useDrawStore((s) => s.setOpen);
  return (
    <span>
      <Button icon="pencil" variant={open ? 'primary' : 'default'} aria-pressed={open} onClick={() => setOpen(!open)}>
        <span className={styles.hideSmall}>Draw</span>
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

  // Open to everyone: Settings are for all, the rest of the dashboard needs a premium account (the drawer says so).
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

  // Visitors can sign in from here; everyone signed in signs out from Settings in the dashboard.
  const account = !loading && !signedIn && isSignInConfigured() ? <Button variant="quiet" onClick={signIn}>Sign in</Button> : null;

  return (
    <header className={styles.top}>
      <div className={styles.brand}>
        <Icon name="globe" size={18} />
        <span className={styles.hideSmall}>GeoIntel</span>
        {premium && <Badge tone="accent">{isDemoPremium() ? 'Premium (demo)' : 'Premium'}</Badge>}
      </div>
      <div className={styles.modesDesktop}>
        <Segmented label="Mode" value={activeMode} onChange={setActiveMode} options={MODES} />
      </div>
      <ModeMenu />
      <div className={styles.spacer} />
      <div className={styles.group}>
        <DrawButton />
        <LayersMenu />
        {dashboard}
        {account}
      </div>
    </header>
  );
}
