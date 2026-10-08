import type { CountryDetail as Detail, CountryStat } from '../../../api/types';
import { formatNumber } from './chart';
import { Unavailable, Fact } from './shared';
import { number } from './format';
import { StatList } from './Stat';
import { Memberships } from './blocks';
import eventStyles from '../EventAnalysis.module.css';
import countryStyles from '../CountryAnalysis.module.css';
import styles from '../CountryDetail.module.css';

const TYPE_LABELS: Record<string, string> = { conflict: 'Conflict', military: 'Military', civil_unrest: 'Civil unrest', proxy: 'Proxy conflict' };
const LEVEL_CLASS = ['advisoryNone', 'advisoryLow', 'advisoryHigh', 'advisoryMax'] as const;

// Reports per week, oldest on the left. The bars are scaled to the busiest week; each carries its date and count for a hover.
function WeeklyBars({ weekly }: { weekly: [string, number][] }) {
  const peak = Math.max(...weekly.map((w) => w[1]), 1);
  return (
    <div className={styles.weekly} role="img" aria-label={`Violent events reported per week, last ${weekly.length} weeks, busiest week ${peak}`}>
      {weekly.map(([start, count]) => (
        <div key={start} className={styles.weekBar} title={`Week of ${start}: ${count}`}>
          <div className={styles.weekFill} style={{ height: `${(count / peak) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function Advisory({ advisory }: { advisory: NonNullable<Detail['advisory']> }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Travel advice (UK government)</div>
      <div className={`${styles.advisory} ${styles[LEVEL_CLASS[Math.min(advisory.level, 3)]]}`}>
        <div className={styles.text}>
          {advisory.alerts.length > 0 ? advisory.alerts.map((a) => a.label).join('. ') : 'No travel warnings in force'}
        </div>
        {advisory.summary.map((line) => (
          <div key={line} className={styles.asOf}>{line}</div>
        ))}
      </div>
      <div className={styles.asOf}>
        {advisory.updated ? `Reviewed ${advisory.updated}. ` : ''}One government&apos;s advice, not a measure of risk.{' '}
        <a href={advisory.url} target="_blank" rel="noopener noreferrer">Full advice</a>. Source: {advisory.source}.
      </div>
    </div>
  );
}

export function Security({ detail }: { detail: Detail }) {
  const conflicts = detail.conflicts;
  const security = detail.security;
  const displaced = detail.displacement?.series ?? [];
  const displacedStats: CountryStat[] = (['refugees', 'idps'] as const)
    .map((field) => {
      const series = displaced.filter((r) => typeof r[field] === 'number').map((r) => [r.year, r[field] as number] as [number, number]);
      if (series.length === 0) return null;
      const [year, value] = series[series.length - 1];
      const label = field === 'refugees' ? 'Refugees from here, living abroad' : 'Displaced inside the country';
      return { code: `displaced-${field}`, label, unit: '', decimals: 0, value, year, series, source: detail.displacement?.source ?? '', rank: null, of: null };
    })
    .filter((s): s is CountryStat => s !== null);
  const empty = !conflicts && !detail.advisory && !(detail.stats && detail.stats.length) && !security && !detail.memberships;
  if (empty) return <Unavailable>Security figures are unavailable for this country.</Unavailable>;
  return (
    <>
      {detail.advisory && <Advisory advisory={detail.advisory} />}
      <div className={styles.group}>
        <div className={styles.groupTitle}>Violence reported in the news</div>
        {conflicts ? (
          <>
            <div className={countryStyles.factsGrid}>
              <Fact label={`Last ${conflicts.days} days`}>{`${number(conflicts.total)} violent events reported`}</Fact>
              <Fact label="Last 7 days">{number(conflicts.last_7_days)}</Fact>
              {Object.entries(conflicts.by_type).map(([type, count]) => (
                <Fact key={type} label={TYPE_LABELS[type] ?? type}>{number(count)}</Fact>
              ))}
            </div>
            {conflicts.weekly && conflicts.weekly.length > 1 && (
              <>
                <WeeklyBars weekly={conflicts.weekly} />
                <div className={styles.asOf}>Reports per week, last {conflicts.weekly.length} weeks (busiest week: {formatNumber(Math.max(...conflicts.weekly.map((w) => w[1])), 0)}).</div>
              </>
            )}
            {conflicts.hotspots && conflicts.hotspots.length > 0 && (
              <div className={styles.group}>
                <div className={styles.groupTitle}>Where reports cluster (last {conflicts.days} days)</div>
                {conflicts.hotspots.map((h) => (
                  <div key={`${h.lat},${h.lon}`} className={styles.mineral}>
                    <div className={styles.shareHead}>
                      <span>{h.name ?? `Near ${h.lat}, ${h.lon}`}</span>
                      <span className={styles.shareValue}>{h.count} reports</span>
                    </div>
                    <div className={styles.asOf}>{h.headline}</div>
                  </div>
                ))}
              </div>
            )}
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
              names in news can occasionally be matched to the wrong country or place.
            </div>
          </>
        ) : (
          <Unavailable>No recent events are tracked for this country.</Unavailable>
        )}
      </div>
      {detail.stats && detail.stats.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Military</div>
          <StatList stats={detail.stats} source="World Bank, from SIPRI" />
        </div>
      )}
      {displacedStats.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Displacement</div>
          <StatList stats={displacedStats} source={detail.displacement?.source} />
        </div>
      )}
      {detail.memberships && detail.memberships.length > 0 && <Memberships memberships={detail.memberships} />}
      <div className={styles.group}>
        <div className={styles.groupTitle}>Armed groups and forces</div>
        {security && (security.terrorist_groups || security.military_branches) ? (
          <div className={countryStyles.factsGrid}>
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
