import { useState } from 'react';
import { ScenariosError } from '../../api/client';
import type { Scenario, ScenarioLikelihood, ScenariosResponse } from '../../api/types';
import PremiumGate from '../../components/PremiumGate';
import { useCrisisScenariosQuery, useEntitlements } from '../../state/queries';
import styles from './Scenarios.module.css';

const LIKELIHOOD_CLASS: Record<ScenarioLikelihood, string> = {
  'less likely': styles.lessLikely,
  plausible: styles.plausible,
  'more likely': styles.moreLikely,
};

function errorMessage(error: unknown): string {
  const kind = error instanceof ScenariosError ? error.kind : 'error';
  switch (kind) {
    case 'sign_in_required':
      return 'Sign in to use scenarios.';
    case 'premium_required':
      return 'Scenarios are a premium feature.';
    case 'unavailable':
      return "Scenario analysis isn't available right now.";
    default:
      return "Couldn't load scenarios. Please try again.";
  }
}

function BulletList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className={styles.detail}>
      <div className={styles.detailLabel}>{label}</div>
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardTitle}>{scenario.title}</div>
        <span className={`${styles.chip} ${LIKELIHOOD_CLASS[scenario.likelihood]}`}>{scenario.likelihood}</span>
      </div>
      {scenario.timeframe && <div className={styles.timeframe}>{scenario.timeframe}</div>}
      <div className={styles.summary}>{scenario.summary}</div>
      <BulletList label="What would drive it" items={scenario.what_would_drive_it} />
      <BulletList label="Watch for" items={scenario.watch_for} />
      <BulletList label="Who is affected" items={scenario.who_is_affected} />
    </div>
  );
}

function basedOnLine(basedOn: ScenariosResponse['based_on']): string {
  const parts = [`severity ${basedOn.severity}/100`];
  if (basedOn.trend && basedOn.trend !== 'insufficient_data') parts.push(`${basedOn.trend} trend`);
  parts.push(basedOn.source_text ? 'source article text' : 'headline only');
  if (basedOn.relationships.length > 0) parts.push(`curated relationship: ${basedOn.relationships.join('; ')}`);
  return parts.join(' · ');
}

// Premium: several ways the situation could unfold. Generated on click (each
// result costs a paid AI call; the server caches it). Rendered with a `key`
// per event so the "requested" state resets when the selection changes.
export default function Scenarios({ crisisId }: { crisisId: string }) {
  const { unlocked: premium } = useEntitlements();
  const [requested, setRequested] = useState(false);
  // Only ever "active" for a premium user; if premium is lost mid-session the
  // section falls back to its locked intro instead of rendering blank.
  const active = requested && premium;
  const { data, isFetching, error, refetch } = useCrisisScenariosQuery(crisisId, active);

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Possible scenarios</div>

      {!active && (
        <>
          <div className={styles.blurb}>
            Several ways this situation could unfold, with what would drive each and what to watch for.
            AI-generated and speculative.
          </div>
          <PremiumGate feature="Scenarios">
            <button type="button" className={styles.action} onClick={() => setRequested(true)}>
              Show scenarios
            </button>
          </PremiumGate>
        </>
      )}

      {active && isFetching && (
        <div className={styles.status}>Analysing this event… this can take up to half a minute.</div>
      )}

      {active && !isFetching && error && (
        <div className={styles.status}>
          {errorMessage(error)}{' '}
          <button type="button" className={styles.link} onClick={() => refetch()}>
            Try again
          </button>
        </div>
      )}

      {active && data && !isFetching && (
        <>
          {data.scenarios.map((scenario) => (
            <ScenarioCard key={scenario.title} scenario={scenario} />
          ))}
          {data.assumptions.length > 0 && <BulletList label="Assumptions" items={data.assumptions} />}
          <div className={styles.basedOn}>Based on: {basedOnLine(data.based_on)}</div>
          <div className={styles.disclaimer}>{data.disclaimer}</div>
        </>
      )}
    </div>
  );
}
