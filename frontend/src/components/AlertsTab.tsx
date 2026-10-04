import { useState } from 'react';
import { UserDataError } from '../api/client';
import type { AlertItem, AlertMinLevel } from '../api/types';
import { ALERT_COLORS, hazardIcon } from '../globe/hazards';
import { timeAgo } from '../lib/time';
import {
  useAlertSettingsQuery,
  useAlertsQuery,
  useMarkAlertsReadMutation,
  useSaveAlertSettingsMutation,
  useStormsQuery,
} from '../state/queries';
import { useUiStore } from '../state/uiStore';
import dashboard from './Dashboard.module.css';
import styles from './Watchlist.module.css';

const LEVELS: { value: AlertMinLevel; label: string }[] = [
  { value: 'green', label: 'All alerts (Green and above)' },
  { value: 'orange', label: 'Orange and Red' },
  { value: 'red', label: 'Red only' },
];

function describeError(error: unknown): string {
  const kind = error instanceof UserDataError ? error.kind : 'error';
  if (kind === 'unavailable') return "Alerts aren't available right now.";
  if (kind === 'sign_in_required') return 'Sign in to see your alerts.';
  if (kind === 'premium_required') return 'Alerts are a premium feature.';
  return "Couldn't load this. Please try again.";
}

// The hazard id is the middle part of "<type>-<id>-<level>".
function hazardIdOf(alert: AlertItem): number | null {
  const id = Number(alert.hazard_key.split('-')[1]);
  return Number.isFinite(id) ? id : null;
}

function Settings() {
  const { data, isLoading } = useAlertSettingsQuery();
  const save = useSaveAlertSettingsMutation();

  if (isLoading || !data) return null;

  return (
    <div className={styles.settings}>
      <label>
        <input
          type="checkbox"
          checked={data.alert_email}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ alert_email: e.target.checked })}
        />
        Email me alerts
      </label>
      <label>
        Alert on
        <select
          value={data.alert_min_level}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ alert_min_level: e.target.value as AlertMinLevel })}
        >
          {LEVELS.map((level) => (
            <option key={level.value} value={level.value}>
              {level.label}
            </option>
          ))}
        </select>
      </label>
      {save.isError && <span className={styles.note}>Couldn&apos;t save that setting.</span>}
    </div>
  );
}

export default function AlertsTab() {
  const { data, isLoading, error } = useAlertsQuery();
  const markRead = useMarkAlertsReadMutation();
  const { data: storms } = useStormsQuery(true);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectHazard = useUiStore((s) => s.selectHazard);
  const setOpen = useUiStore((s) => s.setDashboardOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const [gone, setGone] = useState<string | null>(null);

  // Open the alert's hazard on the globe in Weather mode, if it is still active.
  function open(alert: AlertItem) {
    if (!alert.read_at) markRead.mutate({ ids: [alert.id] });
    const id = hazardIdOf(alert);
    const hazard = storms?.storms.find((s) => s.id === id && s.event_type === alert.hazard_type);
    if (!hazard) {
      setGone(alert.id);
      return;
    }
    setGone(null);
    setActiveMode('weather');
    selectHazard(hazard);
    setOpen(false);
    setRightOpen(true);
  }

  if (isLoading) return <div className={dashboard.status}>Loading…</div>;
  if (error) return <div className={dashboard.status}>{describeError(error)}</div>;
  if (!data) return null;

  return (
    <div>
      <Settings />
      <div className={dashboard.summary}>
        {data.unread} unread
        {data.unread > 0 && (
          <button
            type="button"
            className={dashboard.action}
            style={{ marginLeft: 12 }}
            disabled={markRead.isPending}
            onClick={() => markRead.mutate({ all: true })}
          >
            Mark all read
          </button>
        )}
      </div>
      {data.alerts.length === 0 ? (
        <div className={dashboard.status}>
          No alerts yet. When a hazard comes within one of your watchlist places&apos; radius, it shows up here.
        </div>
      ) : (
        <ul className={dashboard.list}>
          {data.alerts.map((alert) => (
            <li key={alert.id} className={styles.alertRow}>
              <span className={`${styles.unread} ${alert.read_at ? styles.read : ''}`} aria-hidden="true" />
              <button type="button" className={styles.alertMain} onClick={() => open(alert)}>
                <span className={dashboard.rowTitle}>
                  {hazardIcon(alert.hazard_type)} {alert.title}
                </span>
                <span className={dashboard.rowMeta}>
                  <span
                    className={dashboard.dot}
                    style={{ backgroundColor: ALERT_COLORS[alert.alert_level] ?? ALERT_COLORS.Unknown }}
                  />
                  {alert.alert_level} alert &middot; {alert.distance_km} km from {alert.place_name ?? 'a removed place'}{' '}
                  &middot; {timeAgo(alert.created_at)}
                </span>
                {gone === alert.id && <span className={styles.note}>That hazard is no longer active.</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
