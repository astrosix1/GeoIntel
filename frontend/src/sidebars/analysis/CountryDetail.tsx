import { useState } from 'react';
import PremiumGate from '../../components/PremiumGate';
import Segmented from '../../ui/Segmented';
import { ScenariosError } from '../../api/client';
import type { CountryProfile } from '../../api/types';
import { useCountryTabQuery, useEntitlements } from '../../state/queries';
import eventStyles from './EventAnalysis.module.css';
import styles from './CountryDetail.module.css';
import AnalystRead from './country/AnalystRead';
import { Economy } from './country/Economy';
import { Geography } from './country/Geography';
import { Government } from './country/Government';
import { Migration } from './country/Migration';
import { People } from './country/People';
import { Security } from './country/Security';

type Tab = 'government' | 'people' | 'migration' | 'economy' | 'security' | 'geography';

const TABS: { value: Tab; label: string; premium: boolean }[] = [
  { value: 'government', label: 'Government', premium: true },
  { value: 'people', label: 'People', premium: true },
  { value: 'migration', label: 'Migration', premium: true },
  { value: 'economy', label: 'Economy', premium: false },
  { value: 'security', label: 'Security', premium: true },
  { value: 'geography', label: 'Geography', premium: false },
];

function errorMessage(error: unknown): string {
  const kind = error instanceof ScenariosError ? error.kind : 'error';
  if (kind === 'sign_in_required') return 'Sign in to see the detailed country facts.';
  if (kind === 'premium_required') return 'Detailed country facts are a premium feature.';
  if (kind === 'unavailable') return 'No detailed facts are available for this country.';
  return "Couldn't load the detailed facts. Please try again.";
}

// Premium country facts under the free profile. Locked viewers see what is inside and a lock; the server enforces it.

export default function CountryDetail({ countryCode, profile }: { countryCode: string; profile: CountryProfile }) {
  const { unlocked } = useEntitlements();
  const [picked, setPicked] = useState<Tab>('government');
  // Free viewers keep Economy (the trade figures) and Geography; the other tabs are premium and shown greyed with a lock note.
  const tab = unlocked || !TABS.find((t) => t.value === picked)?.premium ? picked : 'economy';
  // Only the open tab's data is fetched, and only for viewers who are unlocked (Geography is the free profile, Economy shows it too).
  const { data, isLoading, error, refetch } = useCountryTabQuery(countryCode, tab, unlocked);
  const options = TABS.map((t) => ({
    value: t.value,
    label: t.label,
    disabled: t.premium && !unlocked,
    hint: t.premium && !unlocked ? 'Premium' : undefined,
  }));

  return (
    <div className={eventStyles.section}>
      <div className={eventStyles.sectionTitle}>Country Facts</div>
      <div className={styles.tabs}>
        <Segmented options={options} value={tab} onChange={setPicked} label="Country facts" size="sm" block grid={3} />
      </div>
      {!unlocked && (
        <div className={styles.group}>
          <PremiumGate feature="Government, People, Migration, Security and the detailed economy facts" block>
            <div className={styles.lockedBox}>Government, People, Migration and Security, and the detailed economy facts.</div>
          </PremiumGate>
        </div>
      )}
      <div role="region" aria-label={`${TABS.find((t) => t.value === tab)?.label} facts`} aria-busy={unlocked && isLoading}>
      {unlocked && isLoading && <div className={eventStyles.loading} role="status">Loading…</div>}
      {unlocked && error && (
        <div className={eventStyles.error} role="alert">
          {errorMessage(error)}{' '}
          <button type="button" className={styles.readButton} onClick={() => refetch()}>Try again</button>
        </div>
      )}
      {tab === 'geography' && <Geography profile={profile} detail={unlocked ? data : undefined} />}
      {tab === 'economy' && <Economy detail={unlocked ? data : undefined} profile={profile} />}
      {data && tab === 'government' && <Government detail={data} />}
      {data && tab === 'people' && <People detail={data} />}
      {data && tab === 'migration' && <Migration detail={data} />}
      {data && tab === 'security' && <Security detail={data} />}
      {unlocked && data && <div className={styles.asOf}>Sources: {data.sources.join(', ')}.</div>}
      {unlocked && data && <AnalystRead key={`${countryCode}:${tab}`} countryCode={countryCode} tab={tab} />}
      </div>
    </div>
  );
}
