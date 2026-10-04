import { isDemoPremium } from './auth/session';
import { useEntitlements } from './state/queries';
import styles from './Logo.module.css';

// Wordmark centred right above the top menu (step 9 of the rewrite plan).
// "GeoIntel" is the app's existing real name, taken from the old index.html's
// <title>. Premium members get a small "Premium" tag inside the same pill;
// everyone else sees just the wordmark.
export default function Logo() {
  const { premium } = useEntitlements();

  return (
    <div className={styles.logo} data-ui-hover-surface>
      <span className={styles.glyph} aria-hidden="true">
        🌐
      </span>
      <span className={styles.wordmark}>GeoIntel</span>
      {premium && <span className={styles.tag}>{isDemoPremium() ? 'Premium (demo)' : 'Premium'}</span>}
    </div>
  );
}
