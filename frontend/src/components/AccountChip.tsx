import { useEntitlements } from '../state/queries';
import { isSignInConfigured, signIn, signOut } from '../auth/session';
import styles from './AccountChip.module.css';

// Small top-left chip under the logo: "Sign in" when anonymous, plan badge +
// sign out when signed in. Renders nothing for anonymous visitors when the
// asix.live login URL isn't configured (nowhere to send them yet).
export default function AccountChip() {
  const { signedIn, premium, loading } = useEntitlements();

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

  return (
    <div className={styles.chip} data-ui-hover-surface>
      <span className={`${styles.plan} ${premium ? styles.premium : ''}`}>{premium ? 'Premium' : 'Free'}</span>
      <button type="button" className={styles.action} onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
