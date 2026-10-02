import type { ReactNode } from 'react';
import { useEntitlements } from '../state/queries';
import { getUpgradeUrl, isSignInConfigured, signIn } from '../auth/session';
import styles from './PremiumGate.module.css';

interface PremiumGateProps {
  children: ReactNode;
  // What the feature is, for the prompt: "Sign in to use {feature}".
  feature: string;
}

// Wrap any premium UI. Premium users get the children untouched. Everyone
// else sees them dimmed and non-interactive with a lock and a prompt: sign in
// if anonymous, upgrade if signed in on the free plan. This is presentation
// only — the matching API routes enforce premium on the server.
export default function PremiumGate({ children, feature }: PremiumGateProps) {
  const { signedIn, premium, loading } = useEntitlements();

  if (premium) return <>{children}</>;

  const upgradeUrl = getUpgradeUrl();

  let prompt: ReactNode = null;
  if (!loading) {
    if (!signedIn) {
      prompt = isSignInConfigured() ? (
        <button type="button" className={styles.cta} onClick={signIn}>
          Sign in to use {feature}
        </button>
      ) : (
        <span className={styles.note}>{feature} is a premium feature</span>
      );
    } else {
      prompt = upgradeUrl ? (
        <a className={styles.cta} href={upgradeUrl}>
          Upgrade to use {feature}
        </a>
      ) : (
        <span className={styles.note}>{feature} is a premium feature</span>
      );
    }
  }

  return (
    <div className={styles.gate}>
      <div className={styles.locked} inert aria-hidden="true">
        {children}
      </div>
      <span className={styles.badge} aria-hidden="true">
        🔒
      </span>
      {prompt && <div className={styles.prompt}>{prompt}</div>}
    </div>
  );
}
