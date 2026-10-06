import CopyLinkButton from '../../components/CopyLinkButton';
import type { Storm } from '../../api/types';
import { hazardIconName } from '../../globe/hazards';
import { useHazardDetailQuery, useHazardEventsQuery } from '../../state/queries';
import { useUiStore } from '../../state/uiStore';
import { labelForSeverity } from '../../globe/severity';
import Icon from '../../ui/Icon';
import { Badge, KeyValue, Section } from '../../ui/Display';
import type { BadgeTone } from '../../ui/Display';
import styles from './EventAnalysis.module.css';

const ALERT_TONE: Record<string, BadgeTone> = { Red: 'alertRed', Orange: 'alertOrange', Green: 'alertGreen' };

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
  const { data: detail, isLoading: detailLoading, isError: detailError } = useHazardDetailQuery(hazard.event_type, hazard.id);
  const { data: linked } = useHazardEventsQuery(hazard.event_type, hazard.id);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const alert = hazard.alert_level ?? 'Unknown';
  const severity = formatSeverity(hazard);
  const from = formatDate(hazard.from_date);
  const to = formatDate(hazard.to_date);
  const updated = formatDate(hazard.date_modified);
  const countries = hazard.affected_countries.length ? hazard.affected_countries : hazard.country ? [hazard.country] : [];

  return (
    <div>
      <h2 className={styles.title}>
        <Icon name={hazardIconName(hazard.event_type)} size={18} /> {hazard.name ?? hazard.hazard ?? 'Weather event'}
      </h2>
      <div className={styles.metaRow}>
        {hazard.hazard && <Badge>{hazard.hazard}</Badge>}
        <Badge tone={ALERT_TONE[alert] ?? 'neutral'}>{alert} alert</Badge>
        {countries.length > 0 && <Badge>{countries.join(', ')}</Badge>}
        <CopyLinkButton target={{ kind: 'hazard', eventType: hazard.event_type, id: hazard.id }} />
      </div>

      {hazard.description && (
        <Section title="Summary">
          <div className={styles.briefingText}>{hazard.description}</div>
        </Section>
      )}

      <Section title="Details">
        <KeyValue
          items={[
            severity ? { label: 'Intensity', value: severity } : null,
            from ? { label: 'Started', value: from } : null,
            to ? { label: hazard.event_type === 'TC' ? 'Latest forecast point' : 'Until', value: to } : null,
            updated ? { label: 'Last updated', value: updated } : null,
          ].filter((item) => item !== null)}
        />
      </Section>

      <Section title="Track and exposure">
        {detailLoading && <span className={styles.loading}>Loading what GDACS publishes for this event...</span>}
        {!detailLoading && (detailError || (detail && detail.unavailable.length > 0)) && (
          <div className={styles.mediaCaption}>
            {detailError || detail?.unavailable.includes('geometry') ? 'Track and area are unavailable right now. ' : ''}
            {detailError || detail?.unavailable.includes('exposure') ? 'Exposure figures are unavailable right now. ' : ''}
            Try again shortly.
          </div>
        )}
        {detail && !detail.unavailable.includes('geometry') && (
          <div className={styles.mediaCaption}>
            {hazard.event_type === 'TC'
              ? detail.track
                ? 'Map: past path (solid), forecast path (dashed), wind zones and the forecast uncertainty cone.'
                : 'GDACS has not published a track for this event.'
              : detail.area
                ? 'Map: the affected area as outlined by GDACS (simplified for display).'
                : 'GDACS has not published an affected area for this event.'}
          </div>
        )}
        {detail?.exposure && detail.exposure.length > 0 && (
          <KeyValue
            items={detail.exposure.map((item) => ({
              label: item.label,
              value: (
                <span title={item.note ?? undefined}>
                  {item.value === null ? 'Not reported' : item.value.toLocaleString()}
                  <span className={styles.sourceOutlet}> {item.basis}</span>
                </span>
              ),
            }))}
          />
        )}
        {detail && !detail.unavailable.includes('exposure') && detail.exposure && detail.exposure.length === 0 && (
          <div className={styles.mediaCaption}>GDACS has not published exposure figures for this event.</div>
        )}
      </Section>

      {linked && linked.events.length > 0 && (
        <Section title={`Events in this area (${linked.events.length}${linked.truncated ? '+' : ''})`}>
          <ul className={styles.sourceList}>
            {linked.events.map((event) => (
              <li key={event.id}>
                <button
                  type="button"
                  className={`${styles.sourceLink} ${styles.linkButton}`}
                  onClick={() => {
                    setActiveMode('events');
                    selectCrisis({
                      id: event.id, title: event.title, country: event.country, type: event.type, severity: event.severity,
                      scope: event.scope, date: event.date ?? '', lat: event.lat, lon: event.lon, source_url: event.source_url ?? '',
                      location_confidence: event.location_confidence ?? undefined,
                    });
                  }}
                >
                  {event.title}
                </button>
                <span className={styles.sourceOutlet}>
                  {event.country} &middot; {labelForSeverity(event.severity)} &middot; {event.approximate ? 'approximate: ' : ''}
                  {event.basis}
                </span>
              </li>
            ))}
          </ul>
          <div className={styles.mediaCaption}>
            Physical events with a city-level or better location, during or just after this hazard. Shown because they share a place and
            time; it does not mean the hazard caused them.
          </div>
        </Section>
      )}

      <Section title="Source">
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
      </Section>
    </div>
  );
}
