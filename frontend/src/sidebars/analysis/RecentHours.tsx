import type { Forecast } from '../../api/types';
import { formatRain, formatTemp } from '../../lib/units';
import type { UnitSystem } from '../../lib/units';
import styles from './EventAnalysis.module.css';
import forecastStyles from './PointForecast.module.css';

// What the weather did here over the hours just gone. These are the forecast model's own values
// for those hours (an analysis), not readings from a weather station, and the panel says so.
export default function RecentHours({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const r = forecast.recent;
  if (!r || r.time.length === 0) return null;
  const rain = r.precipitation ?? [];
  const temps = (r.temperature_2m ?? []).filter((t) => typeof t === 'number');
  const total = rain.reduce<number>((sum, v) => sum + (typeof v === 'number' ? v : 0), 0);
  const peak = Math.max(0.1, ...rain.filter((v) => typeof v === 'number'));

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Last {r.time.length} hours</div>
      <dl className={forecastStyles.facts}>
        <dt>Rain</dt>
        <dd>{formatRain(total, units)}</dd>
        {temps.length > 0 && (
          <>
            <dt>Temperature</dt>
            <dd>
              {formatTemp(Math.min(...temps), units)} to {formatTemp(Math.max(...temps), units)}
            </dd>
          </>
        )}
      </dl>
      {rain.length > 0 && (
        <div
          role="img"
          aria-label={`Hourly rain over the last ${r.time.length} hours, ${formatRain(total, units)} in total`}
          style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 36, marginTop: 6 }}
        >
          {rain.map((value, i) => (
            <span
              key={r.time[i]}
              title={`${r.time[i].slice(11, 16)}: ${formatRain(value, units)}`}
              style={{
                flex: 1,
                minHeight: 2,
                height: `${Math.max(6, ((value ?? 0) / peak) * 100)}%`,
                background: (value ?? 0) > 0 ? 'var(--sky)' : 'var(--raised-strong)',
                borderRadius: 2,
              }}
            />
          ))}
        </div>
      )}
      <div className={styles.mediaCaption}>
        The model&apos;s analysis of the hours just gone, not readings from a weather station. Bars are hourly rain, oldest
        on the left.
      </div>
    </div>
  );
}
