import type { CountryDetail as Detail } from '../../../api/types';
import { Unavailable, Fact, ShareList, Ages } from './shared';
import { rate } from './format';
import { StatList } from './Stat';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

export function People({ detail }: { detail: Detail }) {
  const people = detail.people;
  if (!people) return <Unavailable>Population breakdowns are unavailable for this country.</Unavailable>;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Key figures</div>
        <StatList stats={detail.stats} />
        <div className={countryStyles.factsGrid}>
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
