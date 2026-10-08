import type { CountryDetail as Detail } from '../../../api/types';
import { Unavailable, Fact } from './shared';
import { number } from './format';
import eventStyles from '../EventAnalysis.module.css';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

const TYPE_LABELS: Record<string, string> = { conflict: 'Conflict', military: 'Military', civil_unrest: 'Civil unrest', proxy: 'Proxy conflict' };

export function Security({ detail }: { detail: Detail }) {
  const conflicts = detail.conflicts;
  const security = detail.security;
  return (
    <>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Current conflicts</div>
        {conflicts ? (
          <>
            <div className={countryStyles.factsGrid}>
              <Fact label={`Last ${conflicts.days} days`}>{`${number(conflicts.total)} violent events reported`}</Fact>
              <Fact label="Last 7 days">{number(conflicts.last_7_days)}</Fact>
              {Object.entries(conflicts.by_type).map(([type, count]) => (
                <Fact key={type} label={TYPE_LABELS[type] ?? type}>{number(count)}</Fact>
              ))}
            </div>
            {conflicts.top_events.length > 0 && (
              <ul className={eventStyles.bullets}>
                {conflicts.top_events.map((event) => (
                  <li key={event.id}>
                    {event.title} <span className={styles.asOf}>({event.date.slice(0, 10)}{event.sources > 1 ? `, ${event.sources} sources` : ''})</span>
                  </li>
                ))}
              </ul>
            )}
            <div className={styles.asOf}>
              From this app&apos;s news-fed events, most severe first. These are media reports, not verified casualty counts, and place
              names in news can occasionally be matched to the wrong country.
            </div>
          </>
        ) : (
          <Unavailable>No recent events are tracked for this country.</Unavailable>
        )}
      </div>
      <div className={styles.group}>
        <div className={styles.groupTitle}>Displacement and armed groups</div>
        {security && Object.values(security).some(Boolean) ? (
          <div className={countryStyles.factsGrid}>
            <Fact label="Refugees">{security.refugees}</Fact>
            <Fact label="Displaced inside the country">{security.idps}</Fact>
            <Fact label="Terrorist groups">{security.terrorist_groups}</Fact>
            <Fact label="Armed forces">{security.military_branches}</Fact>
          </div>
        ) : (
          <Unavailable>The Factbook lists nothing here for this country.</Unavailable>
        )}
      </div>
    </>
  );
}
