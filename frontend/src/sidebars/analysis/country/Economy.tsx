import type { CountryDetail as Detail, CountryProfile } from '../../../api/types';
import { Unavailable, Fact, ShareList } from './shared';
import eventStyles from '../EventAnalysis.module.css';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

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

function Trade({ profile }: { profile: CountryProfile }) {
  const { trade } = profile;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Trade and exports</div>
      <div className={countryStyles.factsGrid}>
        <span className={countryStyles.factLabel}>GDP</span>
        <span className={countryStyles.factValue}>
          {trade.gdp_usd_billions ? `$${trade.gdp_usd_billions.toLocaleString()}B (${trade.gdp_year})` : 'unavailable'}
        </span>
        <span className={countryStyles.factLabel}>Exports (% of GDP)</span>
        <span className={countryStyles.factValue}>{trade.exports_percent_of_gdp ?? 'unavailable'}</span>
        <span className={countryStyles.factLabel}>Imports (% of GDP)</span>
        <span className={countryStyles.factValue}>{trade.imports_percent_of_gdp ?? 'unavailable'}</span>
        <span className={countryStyles.factLabel}>Trade openness</span>
        <span className={countryStyles.factValue}>
          {trade.trade_openness_percent_of_gdp != null ? `${trade.trade_openness_percent_of_gdp}% of GDP` : 'unavailable'}
        </span>
      </div>
      {trade.top_exports_by_commodity ? (
        <ul className={eventStyles.bullets}>
          {trade.top_exports_by_commodity.map((exp) => (
            <li key={exp.hs4}>
              HS {exp.hs4} - ${exp.trade_value_usd.toLocaleString()}
            </li>
          ))}
        </ul>
      ) : (
        <div className={`${countryStyles.unavailable} ${eventStyles.gap}`}>
          {trade.top_exports_unavailable_reason ?? 'Top exports by commodity are unavailable for this country.'}
        </div>
      )}
    </div>
  );
}

function Contribution({ profile }: { profile: CountryProfile }) {
  const text = profile.narrative.world_contribution;
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Contribution to the world</div>
      {text ? (
        <div className={eventStyles.briefingText}>{text}</div>
      ) : (
        <Unavailable>No generated narrative is available. See the real GDP and trade figures above.</Unavailable>
      )}
    </div>
  );
}

export function Economy({ detail, profile }: { detail: Detail | undefined; profile: CountryProfile }) {
  const eco = detail?.economy;
  const infra = detail?.infrastructure;
  if (!detail) {
    return (
      <>
        <Trade profile={profile} />
        <Contribution profile={profile} />
      </>
    );
  }
  return (
    <>
      <Trade profile={profile} />
      <Contribution profile={profile} />
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
