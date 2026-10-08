import type { CountryDetail as Detail } from '../../../api/types';
import { Unavailable, Fact } from './shared';
import { number, rate } from './format';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

const countryName = (code: string) => {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
};

export function Migration({ detail }: { detail: Detail }) {
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
          <Fact label="Net migration">{rate(detail.net_migration_rate, 'per 1,000')}</Fact>
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
