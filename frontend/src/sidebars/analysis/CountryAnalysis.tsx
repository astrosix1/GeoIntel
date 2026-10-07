import { useEffect, useState } from 'react';
import { useCountryProfileQuery } from '../../state/queries';
import CountryDetail from './CountryDetail';
import eventStyles from './EventAnalysis.module.css';
import styles from './CountryAnalysis.module.css';

export default function CountryAnalysis({ countryCode }: { countryCode: string }) {
  const { data: profile, isLoading, isError } = useCountryProfileQuery(countryCode);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [profile?.image?.src]);

  if (isLoading) {
    return <div className={eventStyles.loading}>Loading country profile…</div>;
  }
  if (isError || !profile) {
    return <div className={eventStyles.error}>Failed to load country profile.</div>;
  }

  const { demographics, demographics_source, trade, narrative } = profile;
  const isAiGenerated = narrative.model !== 'static-facts-only';

  return (
    <div>
      {demographics.flag_svg && (
        <img className={styles.flag} src={demographics.flag_svg} alt={`Flag of ${demographics.name}`} />
      )}
      <h2 className={eventStyles.title}>{demographics.name ?? profile.country_code}</h2>

      {profile.image && !imageFailed && (
        <div className={eventStyles.section}>
          <img
            className={eventStyles.media}
            src={profile.image.src}
            alt={profile.image.caption || demographics.name || profile.country_code}
            onError={() => setImageFailed(true)}
          />
          {profile.image.caption && (
            <div className={eventStyles.mediaCaption}>{profile.image.caption}</div>
          )}
        </div>
      )}
      <div className={eventStyles.metaRow}>
        {demographics.region && <span className={eventStyles.badge}>{demographics.region}</span>}
        {demographics.capital && <span className={eventStyles.badge}>Capital: {demographics.capital}</span>}
      </div>

      <div className={eventStyles.section}>
        <div className={eventStyles.sectionTitle}>Demographics &amp; Geography</div>
        <div className={styles.factsGrid}>
          <span className={styles.factLabel}>Population</span>
          <span className={styles.factValue}>
            {demographics.population ? demographics.population.toLocaleString() : 'unavailable'}
          </span>
          <span className={styles.factLabel}>Area</span>
          <span className={styles.factValue}>
            {demographics.area_km2 ? `${Math.round(demographics.area_km2).toLocaleString()} km²` : 'unavailable'}
          </span>
          {demographics.borders && demographics.borders.length > 0 && (
            <>
              <span className={styles.factLabel}>Borders</span>
              <span className={styles.factValue}>{demographics.borders.join(', ')}</span>
            </>
          )}
          {demographics.languages && demographics.languages.length > 0 && (
            <>
              <span className={styles.factLabel}>Languages</span>
              <span className={styles.factValue}>{demographics.languages.join(', ')}</span>
            </>
          )}
        </div>
        <div className={`${styles.unavailable} ${eventStyles.gap}`}>
          Source: {demographics_source}
        </div>
      </div>

      <CountryDetail countryCode={countryCode} />

      <div className={eventStyles.section}>
        <div className={eventStyles.sectionTitle}>Geography &amp; Infrastructure</div>
        <span className={`${styles.narrativeBadge} ${isAiGenerated ? styles.aiBadge : styles.staticBadge}`}>
          {isAiGenerated ? 'AI-generated' : 'Real facts, no narrative'}
        </span>
        {narrative.geography_infrastructure ? (
          <div className={eventStyles.briefingText}>{narrative.geography_infrastructure}</div>
        ) : (
          <div className={styles.unavailable}>
            No AI key is configured in this environment, so no generated narrative is shown here —
            see the real structured facts above and below instead.
          </div>
        )}
      </div>

      <div className={eventStyles.section}>
        <div className={eventStyles.sectionTitle}>Trade &amp; Exports</div>
        <div className={styles.factsGrid}>
          <span className={styles.factLabel}>GDP</span>
          <span className={styles.factValue}>
            {trade.gdp_usd_billions ? `$${trade.gdp_usd_billions.toLocaleString()}B (${trade.gdp_year})` : 'unavailable'}
          </span>
          <span className={styles.factLabel}>Exports (% of GDP)</span>
          <span className={styles.factValue}>{trade.exports_percent_of_gdp ?? 'unavailable'}</span>
          <span className={styles.factLabel}>Imports (% of GDP)</span>
          <span className={styles.factValue}>{trade.imports_percent_of_gdp ?? 'unavailable'}</span>
          <span className={styles.factLabel}>Trade openness</span>
          <span className={styles.factValue}>
            {trade.trade_openness_percent_of_gdp != null ? `${trade.trade_openness_percent_of_gdp}% of GDP` : 'unavailable'}
          </span>
        </div>

        {trade.top_exports_by_commodity ? (
          <ul className={eventStyles.bullets}>
            {trade.top_exports_by_commodity.map((exp) => (
              <li key={exp.hs4}>
                HS {exp.hs4} — ${exp.trade_value_usd.toLocaleString()}
              </li>
            ))}
          </ul>
        ) : (
          <div className={`${styles.unavailable} ${eventStyles.gap}`}>
            {trade.top_exports_unavailable_reason ?? 'Top exports by commodity are unavailable for this country.'}
          </div>
        )}
      </div>

      <div className={eventStyles.section}>
        <div className={eventStyles.sectionTitle}>Contribution to the World</div>
        {narrative.world_contribution ? (
          <div className={eventStyles.briefingText}>{narrative.world_contribution}</div>
        ) : (
          <div className={styles.unavailable}>
            No generated narrative available — see the real GDP/trade figures above.
          </div>
        )}
      </div>
    </div>
  );
}
