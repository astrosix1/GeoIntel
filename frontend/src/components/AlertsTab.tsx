import { useState } from 'react';
import { fetchCrisisDetail, UserDataError } from '../api/client';
import type { AlertItem } from '../api/types';
import { alertTone, hazardIconName } from '../globe/hazards';
import Icon from '../ui/Icon';
import { Badge } from '../ui/Display';
import { timeAgo } from '../lib/time';
import {
  useAlertsQuery,
  useMarkAlertsReadMutation,
  useStormsQuery,
} from '../state/queries';
import { useUiStore } from '../state/uiStore';
import dashboard from './Dashboard.module.css';
import styles from './Watchlist.module.css';

function describeError(error: unknown): string {
  const kind = error instanceof UserDataError ? error.kind : 'error';
  if (kind === 'unavailable') {
    const setup = error instanceof UserDataError && (error.reason === 'table_missing' || error.reason === 'column_missing');
    return setup ? "Alerts haven't been set up on the server yet. Please try again later." : "Alerts aren't available right now.";
  }
  if (kind === 'sign_in_required') return 'Sign in to see your alerts.';
  if (kind === 'premium_required') return 'Alerts are a premium feature.';
  return "Couldn't load this. Please try again.";
}

// A situation alert's key is "SIT-<event id>-<level>"; the event id can itself contain dashes.
function eventIdOf(alert: AlertItem): string | null {
  const match = /^SIT-(.+)-(?:green|orange|red)$/.exec(alert.hazard_key);
  return match ? match[1] : null;
}

// The hazard id is the middle part of "<type>-<id>-<level>".
function hazardIdOf(alert: AlertItem): number | null {
  const id = Number(alert.hazard_key.split('-')[1]);
  return Number.isFinite(id) ? id : null;
}

export default function AlertsTab() {
  const { data, isLoading, error } = useAlertsQuery();
  const markRead = useMarkAlertsReadMutation();
  const { data: storms } = useStormsQuery(true);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectHazard = useUiStore((s) => s.selectHazard);
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const setOpen = useUiStore((s) => s.setDashboardOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const [gone, setGone] = useState<string | null>(null);

  // Open the alert's hazard on the globe in Weather mode, if it is still active.
  function open(alert: AlertItem) {
    if (!alert.read_at) markRead.mutate({ ids: [alert.id] });
    if (alert.hazard_type === 'WX' || alert.hazard_type === 'CLK') return;   // a forecast or clock alert has nothing to open
    if (alert.hazard_type === 'SIT') {
      const eventId = eventIdOf(alert);
      if (!eventId) return;
      fetchCrisisDetail(eventId)
        .then((event) => {
          setGone(null);
          setActiveMode('events');
          selectCrisis(event);
          setOpen(false);
          setRightOpen(true);
        })
        .catch(() => setGone(alert.id));
      return;
    }
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
      <div className={dashboard.summary}>
        {data.unread} unread
        {data.unread > 0 && (
          <button
            type="button"
            className={`${dashboard.action} ${styles.afterText}`}
            disabled={markRead.isPending}
            onClick={() => markRead.mutate({ all: true })}
          >
            Mark all read
          </button>
        )}
      </div>
      {data.alerts.length === 0 ? (
        <div className={dashboard.status}>
          No alerts yet. Hazards, forecast limits, situations and clock changes you chose for your watchlist places show up here.
        </div>
      ) : (
        <ul className={dashboard.list}>
          {data.alerts.map((alert) => (
            <li key={alert.id} className={styles.alertRow}>
              <span className={`${styles.unread} ${alert.read_at ? styles.read : ''}`} aria-hidden="true" />
              <button type="button" className={styles.alertMain} onClick={() => open(alert)}>
                <span className={dashboard.rowTitle}>
                  <Icon name={hazardIconName(alert.hazard_type)} size={14} /> {alert.title}
                </span>
                <span className={dashboard.rowMeta}>
                  <Badge compact tone={alertTone(alert.alert_level)}>{alert.alert_level}</Badge>
                  {alert.hazard_type === 'WX'
                    ? `Forecast alert · ${alert.place_name ?? 'a removed place'}`
                    : alert.hazard_type === 'CLK'
                      ? `Clock change · ${alert.place_name ?? 'a removed place'}`
                      : alert.hazard_type === 'SIT'
                        ? `Situation · ${alert.distance_km} km from ${alert.place_name ?? 'a removed place'}`
                        : `${alert.alert_level} alert · ${alert.distance_km} km from ${alert.place_name ?? 'a removed place'}`}{' '}
                  &middot; {timeAgo(alert.created_at)}
                </span>
                {gone === alert.id && alert.hazard_type !== 'WX' && alert.hazard_type !== 'CLK' && (
                  <span className={styles.note}>{alert.hazard_type === 'SIT' ? 'That event is no longer available.' : 'That hazard is no longer active.'}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
