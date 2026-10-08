import { useState } from 'react';
import PremiumGate from '../../components/PremiumGate';
import Segmented from '../../ui/Segmented';
import { ScenariosError } from '../../api/client';
import type { AgeBand, CountryDetail as Detail, Rate, ShareItem, Shares } from '../../api/types';
import { useCountryDetailQuery, useEntitlements } from '../../state/queries';
import eventStyles from './EventAnalysis.module.css';
import countryStyles from './CountryAnalysis.module.css';
import styles from './CountryDetail.module.css';

type Tab = 'government' | 'people' | 'migration' | 'economy';
const TABS: { value: Tab; label: string }[] = [
  { value: 'government', label: 'Government' },
  { value: 'people', label: 'People' },
  { value: 'migration', label: 'Migration' },
  { value: 'economy', label: 'Economy' },
];

const number = (value: number) => value.toLocaleString();

function Unavailable({ children }: { children: string }) {
  return <div className={countryStyles.unavailable}>{children}</div>;
}

// One label and value in the facts grid; nothing at all when the source gave no value.
function Fact({ label, children }: { label: string; children: string | null | undefined }) {
  if (!children) return null;
  return (
    <>
      <span className={countryStyles.factLabel}>{label}</span>
      <span className={countryStyles.factValue}>{children}</span>
    </>
  );
}

function ShareRow({ item, child = false }: { item: ShareItem; child?: boolean }) {
  const percent = `${item.under ? '<' : ''}${item.percent}%`;
  return (
    <div className={`${styles.share} ${child ? styles.child : ''}`}>
      <div className={styles.shareHead}>
        <span>{item.name}</span>
        <span className={styles.shareValue}>
          {percent}
          {item.estimated_count != null && ` · ≈${number(item.estimated_count)}`}
        </span>
      </div>
      <div className={`${styles.bar} ${child ? styles.childBar : ''}`} aria-hidden="true">
        <div className={styles.fill} style={{ width: `${Math.min(item.percent, 100)}%` }} />
      </div>
      {item.children?.map((sub) => <ShareRow key={sub.name} item={sub} child />)}
    </div>
  );
}

function ShareList({ title, shares }: { title: string; shares: Shares | null | undefined }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>{title}</div>
      {shares ? (
        <>
          {shares.items.map((item) => <ShareRow key={item.name} item={item} />)}
          <div className={styles.asOf}>
            {shares.as_of ? `Estimate for ${shares.as_of}. ` : ''}{shares.items.some((item) => item.estimated_count != null) && 'Head counts (≈) are the percentage applied to the population.'}
          </div>
          {shares.note && <div className={styles.asOf}>{shares.note}</div>}
        </>
      ) : (
        <Unavailable>{`No ${title.toLowerCase()} breakdown is published for this country.`}</Unavailable>
      )}
    </div>
  );
}

function Ages({ bands }: { bands: AgeBand[] | null | undefined }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Age groups</div>
      {bands ? (
        <>
          {bands.map((band) => (
            <ShareRow
              key={band.band}
              item={{ name: band.band, percent: band.percent, under: false, estimated_count: band.count ?? undefined }}
            />
          ))}
          <div className={styles.asOf}>Counts are the Factbook&apos;s own.</div>
        </>
      ) : (
        <Unavailable>Age structure is unavailable for this country.</Unavailable>
      )}
    </div>
  );
}

function rate(value: Rate | null | undefined, unit: string): string | null {
  return value ? `${value.value} ${unit}${value.as_of ? ` (${value.as_of})` : ''}` : null;
}

function Government({ detail }: { detail: Detail }) {
  const gov = detail.government;
  if (!gov) return <Unavailable>Government facts are unavailable for this country.</Unavailable>;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Leadership</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="System">{gov.type}</Fact>
          <Fact label="Head of state">{gov.chief_of_state?.text}</Fact>
          <Fact label="Head of government">{gov.head_of_government?.text}</Fact>
          <Fact label="Cabinet">{gov.cabinet}</Fact>
          <Fact label="How chosen">{gov.election_process}</Fact>
        </div>
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Constitution and powers</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="Constitution">{gov.constitution.history}</Fact>
          <Fact label="Amending it">{gov.constitution.amendment}</Fact>
          <Fact label="Legislature">{gov.legislative}</Fact>
          <Fact label="Courts">{gov.judicial}</Fact>
          <Fact label="Legal system">{gov.legal_system}</Fact>
          <Fact label="Voting">{gov.suffrage}</Fact>
          <Fact label="Parties">{gov.parties}</Fact>
        </div>
      </div>
      <div className={styles.asOf}>Leaders are as of the Factbook&apos;s last update and can lag recent changes.</div>
    </>
  );
}

function People({ detail }: { detail: Detail }) {
  const people = detail.people;
  if (!people) return <Unavailable>Population breakdowns are unavailable for this country.</Unavailable>;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Population</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="Total">{detail.population ? `${number(detail.population)} (${detail.population_year})` : null}</Fact>
          <Fact label="Birth rate">{rate(people.birth_rate, 'births per 1,000')}</Fact>
          <Fact label="Death rate">{rate(people.death_rate, 'deaths per 1,000')}</Fact>
          <Fact label="Net migration">{rate(people.net_migration_rate, 'per 1,000')}</Fact>
          <Fact label="Median age">{people.median_age}</Fact>
          <Fact label="Languages">{people.languages}</Fact>
        </div>
      </div>
      <Ages bands={people.age_structure} />
      <ShareList title="Religions" shares={people.religions} />
      {people.ethnic_groups ? (
        <ShareList title="Ethnic groups" shares={people.ethnic_groups} />
      ) : (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Ethnic groups</div>
          {people.ethnic_groups_text ? (
            <>
              <div className={styles.text}>{people.ethnic_groups_text}</div>
              <div className={styles.asOf}>No percentages are published, so none are shown.</div>
            </>
          ) : (
            <Unavailable>No ethnic breakdown is published for this country.</Unavailable>
          )}
        </div>
      )}
    </>
  );
}

const countryName = (code: string) => {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
};

function Migration({ detail }: { detail: Detail }) {
  const mig = detail.migration;
  if (!mig) return <Unavailable>Immigration figures are unavailable for this country.</Unavailable>;
  const largest = mig.origins[0]?.count ?? 1;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Immigrants living here</div>
        <div className={countryStyles.factsGrid}>
          <Fact label="Total">{`${number(mig.migrant_stock)} (${mig.migrant_stock_year})`}</Fact>
          <Fact label="Share of population">{mig.share_of_population != null ? `${mig.share_of_population}%` : null}</Fact>
          <Fact label="Net migration">{rate(detail.people?.net_migration_rate, 'per 1,000')}</Fact>
        </div>
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Where they come from</div>
        {mig.origins.map((origin) => (
          <div key={origin.country_code} className={styles.share}>
            <div className={styles.shareHead}>
              <span>{countryName(origin.country_code)}</span>
              <span className={styles.shareValue}>
                {number(origin.count)}
                {origin.percent_of_migrants != null && ` · ${origin.percent_of_migrants}%`}
              </span>
            </div>
            <div className={styles.bar} aria-hidden="true">
              <div className={styles.fill} style={{ width: `${(origin.count / largest) * 100}%` }} />
            </div>
          </div>
        ))}
        {mig.other_count != null && mig.other_count > 0 && (
          <div className={styles.asOf}>All other origins combined: {number(mig.other_count)}.</div>
        )}
        <div className={styles.asOf}>Bars are relative to the largest origin. Largest {mig.origins.length} origins shown ({mig.year}).</div>
      </div>
    </>
  );
}

function ListBlock({ title, list, note }: { title: string; list: { items: string[]; as_of: number | null } | null | undefined; note?: string }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>{title}</div>
      {list ? (
        <>
          <div className={styles.text}>{list.items.join(', ')}</div>
          {(list.as_of || note) && <div className={styles.asOf}>{[list.as_of ? `As of ${list.as_of}.` : '', note].filter(Boolean).join(' ')}</div>}
        </>
      ) : (
        <Unavailable>{`${title} are unavailable for this country.`}</Unavailable>
      )}
    </div>
  );
}

function Economy({ detail }: { detail: Detail }) {
  const eco = detail.economy;
  const infra = detail.infrastructure;
  if (!eco && !infra) return <Unavailable>Economy and infrastructure facts are unavailable for this country.</Unavailable>;
  return (
    <>
      <ListBlock title="Main exports" list={eco?.exports} />
      <ListBlock title="Main imports" list={eco?.imports} />
      {eco?.export_partners && <ShareList title="Top export partners" shares={eco.export_partners} />}
      {eco?.import_partners && <ShareList title="Top import partners" shares={eco.import_partners} />}
      <ListBlock title="Natural resources and minerals" list={eco?.natural_resources} note="Lists what is found there, not how much is produced." />
      <div className={styles.group}>
        <div className={styles.groupTitle}>Vital infrastructure</div>
        {infra && Object.values(infra).some(Boolean) ? (
          <div className={countryStyles.factsGrid}>
            <Fact label="Airports">{infra.airports}</Fact>
            <Fact label="Seaports">{infra.ports}</Fact>
            <Fact label="Key ports">{infra.key_ports}</Fact>
            <Fact label="Railways">{infra.railways}</Fact>
            <Fact label="Electricity access">{infra.electricity_access}</Fact>
          </div>
        ) : (
          <Unavailable>Infrastructure figures are unavailable for this country.</Unavailable>
        )}
      </div>
    </>
  );
}

function errorMessage(error: unknown): string {
  const kind = error instanceof ScenariosError ? error.kind : 'error';
  if (kind === 'sign_in_required') return 'Sign in to see the detailed country facts.';
  if (kind === 'premium_required') return 'Detailed country facts are a premium feature.';
  if (kind === 'unavailable') return 'No detailed facts are available for this country.';
  return "Couldn't load the detailed facts. Please try again.";
}

// Premium country facts under the free profile. Locked viewers see what is inside and a lock; the server enforces it.
export default function CountryDetail({ countryCode }: { countryCode: string }) {
  const { unlocked } = useEntitlements();
  const [tab, setTab] = useState<Tab>('government');
  const { data, isLoading, error } = useCountryDetailQuery(countryCode, unlocked);

  if (!unlocked) {
    return (
      <div className={eventStyles.section}>
        <div className={eventStyles.sectionTitle}>Country Facts</div>
        <PremiumGate feature="Detailed country facts" block>
          <div className={styles.lockedBox}>Leaders and constitution, population breakdowns, immigration origins, trade, resources and infrastructure.</div>
        </PremiumGate>
      </div>
    );
  }

  return (
    <div className={eventStyles.section}>
      <div className={eventStyles.sectionTitle}>Country Facts</div>
      <div className={styles.tabs}>
        <Segmented options={TABS} value={tab} onChange={setTab} label="Country facts" size="sm" block />
      </div>
      {isLoading && <div className={eventStyles.loading}>Loading…</div>}
      {error && <div className={eventStyles.error}>{errorMessage(error)}</div>}
      {data && tab === 'government' && <Government detail={data} />}
      {data && tab === 'people' && <People detail={data} />}
      {data && tab === 'migration' && <Migration detail={data} />}
      {data && tab === 'economy' && <Economy detail={data} />}
      {data && <div className={styles.asOf}>Sources: {data.sources.join(', ')}.</div>}
    </div>
  );
}
