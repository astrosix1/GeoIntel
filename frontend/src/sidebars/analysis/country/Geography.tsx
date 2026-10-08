import type { CountryProfile } from '../../../api/types';
import { Unavailable } from './shared';
import eventStyles from '../EventAnalysis.module.css';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

export function Geography({ profile }: { profile: CountryProfile }) {
  const { demographics, demographics_source, narrative } = profile;
  const isAiGenerated = narrative.model !== 'static-facts-only';
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Land</div>
        <div className={countryStyles.factsGrid}>
          <span className={countryStyles.factLabel}>Area</span>
          <span className={countryStyles.factValue}>
            {demographics.area_km2 ? `${Math.round(demographics.area_km2).toLocaleString()} km²` : 'unavailable'}
          </span>
          {demographics.borders && demographics.borders.length > 0 && (
            <>
              <span className={countryStyles.factLabel}>Borders</span>
              <span className={countryStyles.factValue}>{demographics.borders.join(', ')}</span>
            </>
          )}
        </div>
        <div className={styles.asOf}>Source: {demographics_source}</div>
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Geography and infrastructure</div>
        <span className={`${countryStyles.narrativeBadge} ${isAiGenerated ? countryStyles.aiBadge : countryStyles.staticBadge}`}>
          {isAiGenerated ? 'AI-generated' : 'Real facts, no narrative'}
        </span>
        {narrative.geography_infrastructure ? (
          <div className={eventStyles.briefingText}>{narrative.geography_infrastructure}</div>
        ) : (
          <Unavailable>No AI key is configured in this environment, so no generated narrative is shown here.</Unavailable>
        )}
      </div>
    </>
  );
}
