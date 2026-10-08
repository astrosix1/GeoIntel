import type { CountryStat } from '../../../api/types';
import { changeText, formatCompact, formatNumber } from './chart';
import Sparkline from './Sparkline';
import styles from './Stat.module.css';

// One figure with its year, its rank among countries, how it has moved, and a trend line. Everything comes from the server's
// stat: nothing here is computed from a guess, and a missing figure is simply not rendered.
export default function Stat({ stat }: { stat: CountryStat }) {
  const change = changeText(stat.series, stat.unit, stat.decimals);
  return (
    <div className={styles.stat}>
      <span className={styles.label}>{stat.label}</span>
      <span className={styles.value}>
        {stat.unit === 'US$' && '$'}
        {stat.compact ? formatCompact(stat.value) : formatNumber(stat.value, stat.decimals)}
        {stat.unit && stat.unit !== 'US$' && <span className={styles.unit}>{stat.unit}</span>}
      </span>
      <div className={styles.meta}>
        <span>{stat.year}</span>
        {stat.rank != null && stat.of != null && <span className={styles.rank}>#{stat.rank} of {stat.of}</span>}
        {change && <span>{change}</span>}
        <Sparkline points={stat.series} label={`${stat.label}, ${stat.series[0][0]} to ${stat.year}`} />
      </div>
    </div>
  );
}

export function StatList({ stats, source }: { stats: CountryStat[] | undefined; source?: string }) {
  if (!stats || stats.length === 0) return null;
  return (
    <div>
      {stats.map((stat) => <Stat key={stat.code} stat={stat} />)}
      <div className={styles.meta}>Source: {source ?? stats[0].source}. Rank: 1 is the highest value among {stats[0].of ?? 'all'} economies.</div>
    </div>
  );
}
