import type { EventAnalysisData } from '../../api/types';
import { Badge, Section } from '../../ui/Display';
import { labelForSeverity } from '../../globe/severity';
import { useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';

// The actors an event involves and the similar recent events. (The country's own figures live in the country analysis.)
export default function EventPattern({ data }: { data: EventAnalysisData }) {
  const { related, parties } = data;
  const selectCountry = useUiStore((st) => st.selectCountry);
  const selectCrisis = useUiStore((st) => st.selectCrisis);
  const stateParties = parties.filter((p) => p.country_code);
  if (related.length === 0 && parties.length === 0) return null;
  return (
    <>
      {parties.length > 0 && (
        <Section title="Parties">
          <div>
            {parties.map((p) =>
              p.country_code ? (
                <button key={p.code} type="button" className={`${styles.sourceLink} ${styles.linkButton}`} onClick={() => selectCountry(p.country_code as string)}>
                  {p.name}
                </button>
              ) : (
                <Badge key={p.code}>{p.name}</Badge>
              ),
            )}
          </div>
          {stateParties.length > 0 && <div className={styles.mediaCaption}>Actors the event involves; a state opens its country analysis.</div>}
        </Section>
      )}
      {related.length > 0 && (
        <Section title="Similar recent events">
          <ul className={styles.sourceList}>
            {related.map((r) => (
              <li key={r.id}>
                <button type="button" className={`${styles.sourceLink} ${styles.linkButton}`} onClick={() => selectCrisis(r)}>
                  {r.title}
                </button>
                <span className={styles.sourceOutlet}>
                  {r.country}, {(r.date ?? '').slice(0, 10)}
                  {r.severity_level ? `, ${labelForSeverity(r.severity)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
