import { useState } from 'react';
import type { Forecast } from '../../api/types';
import { compass, formatRain, formatSpeed, formatTemp } from '../../lib/units';
import type { UnitSystem } from '../../lib/units';
import { describeWeather } from '../../lib/weatherCodes';
import styles from './EventAnalysis.module.css';
import forecastStyles from './PointForecast.module.css';

// "Mon 14:00" from a local ISO time such as "2026-10-05T14:00" (already in the place's own timezone).
function slotLabel(iso: string, index: number): string {
  if (index === 0) return 'Now';
  const day = new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
  return `${day}, ${iso.slice(11, 16)}`;
}

// Step through every forecast hour (up to 7 days). All values are the provider's
// forecast for that hour, not observations, and the panel says so.
export default function ForecastTimeline({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const h = forecast.hourly;
  const [index, setIndex] = useState(0);
  if (h.time.length < 2) return null;
  const i = Math.min(index, h.time.length - 1);
  const sky = describeWeather(h.weather_code?.[i]);
  const rainChance = h.precipitation_probability?.[i];
  const hoursAhead = i;

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Forecast timeline</div>
      <input
        type="range"
        min={0}
        max={h.time.length - 1}
        step={1}
        value={i}
        onChange={(e) => setIndex(Number(e.target.value))}
        className={forecastStyles.scrubber}
        aria-label="Forecast hour"
        aria-valuetext={slotLabel(h.time[i], i)}
      />
      <div className={forecastStyles.timelineHead}>
        <strong>{slotLabel(h.time[i], i)}</strong>
        <span className={forecastStyles.low}>{hoursAhead === 0 ? 'current hour' : `${hoursAhead} h ahead`}</span>
      </div>
      <div className={forecastStyles.nowRow}>
        <span className={forecastStyles.nowIcon} aria-hidden="true">
          {sky.icon}
        </span>
        <div>
          <div className={forecastStyles.nowTemp}>{formatTemp(h.temperature_2m?.[i], units)}</div>
          <div className={forecastStyles.nowLabel}>{sky.label}</div>
        </div>
      </div>
      <dl className={forecastStyles.facts}>
        <dt>Rain</dt>
        <dd>
          {formatRain(h.precipitation?.[i], units)}
          {rainChance != null && ` · ${rainChance}% chance`}
        </dd>
        <dt>Wind</dt>
        <dd>{h.wind_speed_10m?.[i] != null ? formatSpeed(h.wind_speed_10m[i], units) : '–'}</dd>
        <dt>Gusts</dt>
        <dd>{h.wind_gusts_10m?.[i] != null ? formatSpeed(h.wind_gusts_10m[i], units) : '–'}</dd>
      </dl>
      <div className={styles.mediaCaption}>
        Forecast, not observed. It gets less certain the further ahead you look.
        {i === 0 && forecast.current.wind_direction_10m != null && ` Wind from the ${compass(forecast.current.wind_direction_10m)}.`}
      </div>
    </div>
  );
}
