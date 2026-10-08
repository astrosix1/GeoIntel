import { useState } from 'react';
import { ScenariosError } from '../../../api/client';
import { useCountryReadQuery } from '../../../state/queries';
import eventStyles from '../EventAnalysis.module.css';
import styles from '../CountryDetail.module.css';

function message(error: unknown): string {
  const kind = error instanceof ScenariosError ? error.kind : 'error';
  if (kind === 'sign_in_required') return 'Sign in to get the analyst read.';
  if (kind === 'premium_required') return 'The analyst read is a premium feature.';
  if (kind === 'unavailable') return "The analyst read isn't available right now.";
  return "Couldn't write the analyst read. Please try again.";
}

// An AI-written paragraph on what stands out in this tab's figures. It costs a model call, so it waits for a click; the
// server keeps each one for a week, so asking again is instant.
export default function AnalystRead({ countryCode, tab }: { countryCode: string; tab: string }) {
  const [asked, setAsked] = useState<string | null>(null);
  const wanted = asked === `${countryCode}:${tab}`;
  const { data, isFetching, error, refetch } = useCountryReadQuery(countryCode, tab, wanted);
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Analyst read</div>
      <div aria-live="polite">
        {!wanted && (
          <button type="button" className={styles.readButton} onClick={() => setAsked(`${countryCode}:${tab}`)}>
            Write an analyst read of this tab
          </button>
        )}
        {wanted && isFetching && <div className={eventStyles.loading}>Reading the figures…</div>}
        {wanted && error && !isFetching && (
          <div className={eventStyles.error}>
            {message(error)}{' '}
            <button type="button" className={styles.readButton} onClick={() => refetch()}>Try again</button>
          </div>
        )}
        {wanted && data && (
          <>
            <div className={styles.text}>{data.text}</div>
            <div className={styles.asOf}>Written by an AI model from the figures on this tab and nothing else. Check it against them.</div>
          </>
        )}
      </div>
    </div>
  );
}
