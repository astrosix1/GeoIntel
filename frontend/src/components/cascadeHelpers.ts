import { getUpgradeUrl } from '../auth/session';

export { CascadeError } from '../api/client';

// The upgrade link, or null when none is configured.
export function getUpgradeUrlSafe(): string | null {
  return getUpgradeUrl() || null;
}
