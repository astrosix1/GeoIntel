import { useState } from 'react';
import { UserDataError } from '../api/client';
import type { AlertItem, AlertMinLevel, AlertSettings, ConditionKey } from '../api/types';
import { alertTone, hazardIconName } from '../globe/hazards';
import Icon from '../ui/Icon';
import { Badge } from '../ui/Display';
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

// The forecast limits a user can switch on. Ranges match the server's own validation.
const CONDITIONS: { key: ConditionKey; label: string; unit: string; fallback: number; min: number; max: number }[] = [
  { key: 'heat_c', label: 'Heat: daily high at or above', unit: '°C', fallback: 38, min: 25, max: 55 },
  { key: 'cold_c', label: 'Cold: daily low at or below', unit: '°C', fallback: -10, min: -60, max: 10 },
  { key: 'rain_mm', label: 'Heavy rain: daily total at or above', unit: 'mm', fallback: 50, min: 10, max: 500 },
  { key: 'gust_kmh', label: 'Strong gusts: at or above', unit: 'km/h', fallback: 90, min: 50, max: 250 },
  { key: 'uv_index', label: 'UV index at or above', unit: '', fallback: 8, min: 6, max: 16 },
];

function ConditionRow({ spec, value, disabled, onSave }: {
  spec: (typeof CONDITIONS)[number];
  value: number | undefined;
  disabled: boolean;
  onSave: (value: number | null) => void;
}) {
  const [text, setText] = useState(value === undefined ? '' : String(value));
  const enabled = value !== undefined;

  function commit() {
    const number = Number(text);
    if (!enabled || text.trim() === '' || !Number.isFinite(number)) return;
    const clamped = Math.min(spec.max, Math.max(spec.min, number));
    setText(String(clamped));
    if (clamped !== value) onSave(clamped);
  }

  return (
    <label>
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={(e) => {
          if (e.target.checked) {
            setText(String(spec.fallback));
            onSave(spec.fallback);
          } else {
            onSave(null);
          }
        }}
      />
      {spec.label}
      <input
        type="number"
        value={text}
        min={spec.min}
        max={spec.max}
        disabled={disabled || !enabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
        }}
        className={styles.numberInput}
        aria-label={`${spec.label} (${spec.unit || 'index'})`}
      />
      {spec.unit}
    </label>
  );
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
      <div>
        <div className={styles.note}>Forecast alerts: tell me when a place&apos;s forecast for the next 3 days passes a limit.</div>
        {CONDITIONS.map((spec) => (
          <ConditionRow
            key={spec.key}
            spec={spec}
            value={data.alert_conditions[spec.key]}
            disabled={save.isPending}
            onSave={(value) => save.mutate({ alert_conditions: { [spec.key]: value } as AlertSettings['alert_conditions'] })}
          />
        ))}
      </div>
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
    if (alert.hazard_type === 'WX') return;   // a forecast alert has no hazard to open
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
          No alerts yet. When a hazard comes within one of your watchlist places&apos; radius, it shows up here.
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
                    : `${alert.alert_level} alert · ${alert.distance_km} km from ${alert.place_name ?? 'a removed place'}`}{' '}
                  &middot; {timeAgo(alert.created_at)}
                </span>
                {gone === alert.id && alert.hazard_type !== 'WX' && <span className={styles.note}>That hazard is no longer active.</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
