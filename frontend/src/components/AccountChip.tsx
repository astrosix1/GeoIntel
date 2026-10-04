import { useEntitlements } from '../state/queries';
import { isSignInConfigured, signIn, signOut } from '../auth/session';
import styles from './AccountChip.module.css';

// Top-left Sign in / Sign out. The plan ("Premium") is shown by the logo, so
// this only appears when there is an action to offer: Sign in for anonymous
// visitors, Sign out for free members (premium members sign out from inside
// their Dashboard, which free members can't open). Anonymous visitors see
// nothing when the asix.live login URL isn't configured (nowhere to send them).
export default function AccountChip() {
  const { signedIn, premium, loading } = useEntitlements();

  if (loading || premium) return null;

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

  return (
    <div className={styles.chip} data-ui-hover-surface>
      <button type="button" className={styles.action} onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
