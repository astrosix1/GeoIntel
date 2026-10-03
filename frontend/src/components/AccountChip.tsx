import { useEntitlements } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import PremiumGate from './PremiumGate';
import { isDemoPremium, isSignInConfigured, signIn, signOut } from '../auth/session';
import styles from './AccountChip.module.css';

// Small top-left chip under the logo: "Sign in" when anonymous, plan badge +
// sign out when signed in. Renders nothing for anonymous visitors when the
// asix.live login URL isn't configured (nowhere to send them yet).
export default function AccountChip() {
  const { signedIn, premium, loading } = useEntitlements();
  const setDashboardOpen = useUiStore((s) => s.setDashboardOpen);

  if (loading) return null;

  if (!signedIn) {
    if (!isSignInConfigured()) return null;
    return (
      <div className={styles.chip} data-ui-hover-surface>
        <button type="button" className={styles.action} onClick={signIn}>
          Sign in
        </button>
      </div>
    );
  }

  // Locked for non-premium visitors, like every premium control.
  const dashboardButton = (
    <button type="button" className={styles.action} onClick={() => setDashboardOpen(true)}>
      Dashboard
    </button>
  );

  return (
    <div className={styles.chip} data-ui-hover-surface>
      <span className={`${styles.plan} ${premium ? styles.premium : ''}`}>
        {premium ? (isDemoPremium() ? 'Premium (demo)' : 'Premium') : 'Free'}
      </span>
      {premium ? dashboardButton : <PremiumGate feature="Dashboard">{dashboardButton}</PremiumGate>}
      <button type="button" className={styles.action} onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
