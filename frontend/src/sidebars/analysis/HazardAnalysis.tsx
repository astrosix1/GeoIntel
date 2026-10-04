import type { Storm } from '../../api/types';
import { ALERT_COLORS, hazardIcon } from '../../globe/hazards';
import styles from './EventAnalysis.module.css';
import hazardStyles from './HazardAnalysis.module.css';

function formatDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatSeverity(hazard: Storm): string | null {
  if (hazard.severity_text) return hazard.severity_text;
  if (hazard.severity == null) return null;
  return `${hazard.severity}${hazard.severity_unit ? ` ${hazard.severity_unit}` : ''}`;
}

// Analysis view for a Weather-mode pin. Everything shown is a real GDACS
// field; anything GDACS didn't report is simply left out.
export default function HazardAnalysis({ hazard }: { hazard: Storm }) {
  const alert = hazard.alert_level ?? 'Unknown';
  const severity = formatSeverity(hazard);
  const from = formatDate(hazard.from_date);
  const to = formatDate(hazard.to_date);
  const updated = formatDate(hazard.date_modified);
  const countries = hazard.affected_countries.length ? hazard.affected_countries : hazard.country ? [hazard.country] : [];

  return (
    <div>
      <h2 className={styles.title}>
        {hazardIcon(hazard.event_type)} {hazard.name ?? hazard.hazard ?? 'Weather event'}
      </h2>
      <div className={styles.metaRow}>
        {hazard.hazard && <span className={styles.badge}>{hazard.hazard}</span>}
        <span className={`${styles.badge} ${styles.severityBadge}`} style={{ background: ALERT_COLORS[alert] ?? ALERT_COLORS.Unknown }}>
          {alert} alert
        </span>
        {countries.length > 0 && <span className={styles.badge}>{countries.join(', ')}</span>}
      </div>

      {hazard.description && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Summary</div>
          <div className={styles.briefingText}>{hazard.description}</div>
        </div>
      )}

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Details</div>
        <dl className={hazardStyles.facts}>
          {severity && (
            <>
              <dt>Intensity</dt>
              <dd>{severity}</dd>
            </>
          )}
          {from && (
            <>
              <dt>Started</dt>
              <dd>{from}</dd>
            </>
          )}
          {to && (
            <>
              <dt>{hazard.event_type === 'TC' ? 'Latest forecast point' : 'Until'}</dt>
              <dd>{to}</dd>
            </>
          )}
          {updated && (
            <>
              <dt>Last updated</dt>
              <dd>{updated}</dd>
            </>
          )}
        </dl>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Source</div>
        {hazard.report_url ? (
          <a className={styles.sourceLink} href={hazard.report_url} target="_blank" rel="noopener noreferrer">
            GDACS report
          </a>
        ) : (
          <span className={styles.loading}>gdacs.org</span>
        )}
        <div className={styles.mediaCaption}>
          Alert levels (Green, Orange, Red) are GDACS&apos;s own classification of expected humanitarian impact.
        </div>
      </div>
    </div>
  );
}
