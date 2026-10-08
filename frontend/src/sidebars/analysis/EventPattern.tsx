import type { EventAnalysisData } from '../../api/types';
import { Section } from '../../ui/Display';
import Sparkline from './country/Sparkline';
import { labelForSeverity } from '../../globe/severity';
import styles from './EventAnalysis.module.css';

const DIRECTION_TEXT = {
  rising: 'Rising: more reports than the week before',
  falling: 'Falling: fewer reports than the week before',
  steady: 'Steady: about the same as the week before',
  too_few: 'Too few reports to call a direction',
} as const;

// "The pattern here": counted from this app's own events, so it says what is counted and where it comes from.
export default function EventPattern({ data }: { data: EventAnalysisData }) {
  const { pattern, related } = data;
  if (!pattern && related.length === 0) return null;
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
      {related.length > 0 && (
        <Section title="Similar recent events">
          <ul className={styles.sourceList}>
            {related.map((r) => (
              <li key={r.id}>
                <span className={styles.sourceLink}>{r.title}</span>
                <span className={styles.sourceOutlet}>
                  {r.country}, {r.date.slice(0, 10)}
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
