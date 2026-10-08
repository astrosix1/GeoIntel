import type { EventAnalysisData } from '../../api/types';
import { Badge, Section } from '../../ui/Display';
import Sparkline from './country/Sparkline';
import { labelForSeverity } from '../../globe/severity';
import { useCountryProfileQuery, useEntitlements } from '../../state/queries';
import { useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';

const DIRECTION_TEXT = {
  rising: 'Rising: more reports than the week before',
  falling: 'Falling: fewer reports than the week before',
  steady: 'Steady: about the same as the week before',
  too_few: 'Too few reports to call a direction',
} as const;

// "The pattern here": counted from this app's own events, so it says what is counted and where it comes from.
export default function EventPattern({ data }: { data: EventAnalysisData }) {
  const { pattern, related, parties } = data;
  const { unlocked: premium } = useEntitlements();
  const selectCountry = useUiStore((st) => st.selectCountry);
  const selectCrisis = useUiStore((st) => st.selectCrisis);
  const { data: profile } = useCountryProfileQuery(data.country_code ?? undefined);
  const demographics = profile?.demographics;
  const stateParties = parties.filter((p) => p.country_code);
  if (!pattern && related.length === 0 && !data.country_code && parties.length === 0) return null;
  return (
    <>
      {pattern && (
        <Section title={`The pattern in ${pattern.country}`}>
          <div className={styles.briefingText}>
            {pattern.last_7_days} violent report{pattern.last_7_days === 1 ? '' : 's'} in the last 7 days, against {pattern.previous_7_days} in the 7 before.{' '}
            {DIRECTION_TEXT[pattern.direction]}.
          </div>
          <Sparkline
            points={pattern.weekly.map(([, count], i) => [i, count])}
            label={`Weekly violent reports in ${pattern.country}, last ${pattern.weekly.length} weeks`}
            width={160}
            height={32}
          />
          <div className={styles.mediaCaption}>Counted: {pattern.counted}. These are media reports, not verified casualty data. Source: {pattern.source}.</div>
        </Section>
      )}
      {data.country_code && (
        <Section title="Country context">
          <div className={styles.briefingText}>
            {[demographics?.name, demographics?.capital && `capital ${demographics.capital}`,
              demographics?.population != null && `population ${demographics.population.toLocaleString('en-US')}`]
              .filter(Boolean).join(', ') || data.country_code}
          </div>
          <button type="button" className={`${styles.sourceLink} ${styles.linkButton}`} onClick={() => selectCountry(data.country_code as string)}>
            Open the country analysis
          </button>
          {!premium && <div className={styles.mediaCaption}>Travel advice, violence trend and leaders are in the country analysis (premium).</div>}
        </Section>
      )}
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
