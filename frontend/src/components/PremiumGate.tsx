import type { ReactNode } from 'react';
import { useEntitlements } from '../state/queries';
import { getUpgradeUrl, isSignInConfigured, signIn } from '../auth/session';
import Icon from '../ui/Icon';
import styles from './PremiumGate.module.css';

interface PremiumGateProps {
  children: ReactNode;
  // What the feature is, for the prompt: "Sign in to use {feature}".
  feature: string;
  // Lay the gate out full-width (for forms) instead of shrink-wrapping its child.
  block?: boolean;
  // The feature is tied to the user's account (saves, comments, watchlist), so it stays locked for anonymous visitors
  // even while the backend's testing switch opens the other premium features.
  account?: boolean;
}

// Wrap any premium UI. Premium users get the children untouched. Everyone
// else sees them dimmed and non-interactive with a lock and a prompt: sign in
// if anonymous, upgrade if signed in on the free plan. This is presentation
// only — the matching API routes enforce premium on the server.
export default function PremiumGate({ children, feature, block, account = false }: PremiumGateProps) {
  const { signedIn, premium, unlocked, loading } = useEntitlements();

  if (account ? premium : unlocked) return <>{children}</>;

  const upgradeUrl = getUpgradeUrl();

  // The lock sits beside the dimmed control. When there is something to do (sign in, upgrade) the lock does it;
  // otherwise it just explains itself on hover and to screen readers.
  let lock: ReactNode = null;
  if (!loading) {
    const note = `${feature} is a premium feature`;
    if (!signedIn && isSignInConfigured()) {
      lock = (
        <button type="button" className={styles.lock} title={`Sign in to use ${feature}`} aria-label={`Sign in to use ${feature}`} onClick={signIn}>
          <Icon name="lock" size={14} />
        </button>
      );
    } else if (signedIn && upgradeUrl) {
      lock = (
        <a className={styles.lock} href={upgradeUrl} title={`Upgrade to use ${feature}`} aria-label={`Upgrade to use ${feature}`}>
          <Icon name="lock" size={14} />
        </a>
      );
    } else {
      lock = (
        <span className={styles.lock} role="img" title={note} aria-label={note}>
          <Icon name="lock" size={14} />
        </span>
      );
    }
  }

  return (
    <div className={`${styles.gate} ${block ? styles.block : ''}`}>
      <div className={styles.locked} inert aria-hidden="true">
        {children}
      </div>
      {lock}
    </div>
  );
}
