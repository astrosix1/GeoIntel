import { useState } from 'react';
import type { Forecast } from '../../api/types';
import { compass, formatRain, formatSpeed, formatTemp, loadUnits, saveUnits } from '../../lib/units';
import type { UnitSystem } from '../../lib/units';
import { describeWeather } from '../../lib/weatherCodes';
import PremiumGate from '../../components/PremiumGate';
import { useEntitlements, useForecastQuery } from '../../state/queries';
import ComparePlaces from './ComparePlaces';
import ForecastTimeline from './ForecastTimeline';
import { MAX_COMPARE_PLACES, useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';
import forecastStyles from './PointForecast.module.css';

function coords(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
}

// Times from the API are already in the place's own timezone ("2026-10-03T14:00").
function hourLabel(iso: string): string {
  const hour = Number(iso.slice(11, 13));
  return `${hour % 12 === 0 ? 12 : hour % 12}${hour < 12 ? 'am' : 'pm'}`;
}

function dayLabel(date: string, index: number): string {
  if (index === 0) return 'Today';
  return new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
}

function Current({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const c = forecast.current;
  const now = describeWeather(c.weather_code);
  return (
    <div className={styles.section}>
      <div className={forecastStyles.nowRow}>
        <span className={forecastStyles.nowIcon} aria-hidden="true">
          {now.icon}
        </span>
        <div>
          <div className={forecastStyles.nowTemp}>{formatTemp(c.temperature_2m, units)}</div>
          <div className={forecastStyles.nowLabel}>
            {now.label} &middot; feels like {formatTemp(c.apparent_temperature, units)}
          </div>
        </div>
      </div>
      <dl className={forecastStyles.facts}>
        <dt>Wind</dt>
        <dd>
          {formatSpeed(c.wind_speed_10m, units)} {compass(c.wind_direction_10m)}
          {c.wind_gusts_10m != null && ` · gusts ${formatSpeed(c.wind_gusts_10m, units)}`}
        </dd>
        <dt>Humidity</dt>
        <dd>{c.relative_humidity_2m != null ? `${Math.round(c.relative_humidity_2m)}%` : '–'}</dd>
        <dt>Rain now</dt>
        <dd>{formatRain(c.precipitation, units)}</dd>
        <dt>Cloud cover</dt>
        <dd>{c.cloud_cover != null ? `${Math.round(c.cloud_cover)}%` : '–'}</dd>
        <dt>Pressure</dt>
        <dd>{c.pressure_msl != null ? `${Math.round(c.pressure_msl)} hPa` : '–'}</dd>
      </dl>
    </div>
  );
}

function Hourly({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const h = forecast.hourly;
  const count = Math.min(24, h.time.length);
  if (count === 0) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>Next 24 hours</div>
      <div className={forecastStyles.hours}>
        {h.time.slice(0, count).map((time, i) => (
          <div key={time} className={forecastStyles.hour}>
            <div className={forecastStyles.hourTime}>{i === 0 ? 'Now' : hourLabel(time)}</div>
            <div aria-hidden="true">{describeWeather(h.weather_code?.[i]).icon}</div>
            <div className={forecastStyles.hourTemp}>{formatTemp(h.temperature_2m?.[i], units)}</div>
            <div className={forecastStyles.hourRain}>
              {h.precipitation_probability?.[i] != null ? `${h.precipitation_probability[i]}%` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Daily({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const d = forecast.daily;
  if (d.time.length === 0) return null;
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>7-day forecast</div>
      <table className={forecastStyles.days}>
        <tbody>
          {d.time.map((date, i) => {
            const w = describeWeather(d.weather_code?.[i]);
            return (
              <tr key={date}>
                <td>{dayLabel(date, i)}</td>
                <td title={w.label}>
                  <span aria-hidden="true">{w.icon}</span>
                  <span className={forecastStyles.srOnly}>{w.label}</span>
                </td>
                <td>
                  {formatTemp(d.temperature_2m_max?.[i], units)}
                  <span className={forecastStyles.low}> / {formatTemp(d.temperature_2m_min?.[i], units)}</span>
                </td>
                <td className={forecastStyles.rain}>
                  {formatRain(d.precipitation_sum?.[i], units)}
                  {d.precipitation_probability_max?.[i] != null && ` · ${d.precipitation_probability_max[i]}%`}
                </td>
                <td className={forecastStyles.gust}>
                  {d.wind_gusts_10m_max?.[i] != null ? formatSpeed(d.wind_gusts_10m_max[i], units) : '–'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className={styles.mediaCaption}>Columns: day, sky, high / low, rain total and chance, strongest gust.</div>
    </div>
  );
}

// Analysis view for a clicked point in Weather mode. All values come straight
// from the forecast provider; anything it didn't return shows as a dash.
export default function PointForecast({ lat, lon, label }: { lat: number; lon: number; label: string | null }) {
  const [units, setUnits] = useState<UnitSystem>(loadUnits);
  const { premium } = useEntitlements();
  const setPendingWatchPoint = useUiStore((s) => s.setPendingWatchPoint);
  const setDashboardTab = useUiStore((s) => s.setDashboardTab);
  const setDashboardOpen = useUiStore((s) => s.setDashboardOpen);
  const { data, isLoading, isError, refetch } = useForecastQuery(lat, lon);
  const comparePlaces = useUiStore((s) => s.comparePlaces);
  const addComparePlace = useUiStore((s) => s.addComparePlace);
  const comparing = comparePlaces.some((p) => p.lat === lat && p.lon === lon);
  const compareFull = comparePlaces.length >= MAX_COMPARE_PLACES;

  function chooseUnits(next: UnitSystem) {
    setUnits(next);
    saveUnits(next);
  }

  function addToWatchlist() {
    if (!premium) return;
    setPendingWatchPoint({ lat: Math.round(lat * 10000) / 10000, lon: Math.round(lon * 10000) / 10000, name: label ?? 'Pinned location' });
    setDashboardTab('watchlist');
    setDashboardOpen(true);
  }

  const watchButton = (
    <button type="button" className={forecastStyles.watchButton} onClick={addToWatchlist}>
      + Add to watchlist
    </button>
  );

  return (
    <div>
      <h2 className={styles.title}>{label ?? 'Forecast'}</h2>
      <div className={styles.metaRow}>
        <span className={styles.badge}>{coords(lat, lon)}</span>
        {data?.elevation_m != null && <span className={styles.badge}>{Math.round(data.elevation_m)} m elevation</span>}
        <span className={forecastStyles.unitToggle} role="group" aria-label="Units">
          {(['metric', 'imperial'] as const).map((u) => (
            <button
              key={u}
              type="button"
              aria-pressed={units === u}
              className={`${forecastStyles.unitButton} ${units === u ? forecastStyles.unitActive : ''}`}
              onClick={() => chooseUnits(u)}
            >
              {u === 'metric' ? '°C' : '°F'}
            </button>
          ))}
        </span>
      </div>

      <div className={forecastStyles.watchRow}>
        {premium ? watchButton : <PremiumGate feature="Watchlist alerts">{watchButton}</PremiumGate>}
        <button
          type="button"
          className={forecastStyles.watchButton}
          disabled={comparing || compareFull}
          title={compareFull && !comparing ? 'Remove a place to add another' : undefined}
          onClick={() => addComparePlace({ lat, lon, label: label ?? coords(lat, lon) })}
        >
          {comparing ? 'In comparison' : '+ Compare'}
        </button>
      </div>
      <ComparePlaces units={units} />

      {isLoading && <div className={styles.loading}>Loading forecast…</div>}
      {isError && (
        <div className={styles.error}>
          Forecast isn&apos;t available right now.{' '}
          <button type="button" className={forecastStyles.retry} onClick={() => refetch()}>
            Try again
          </button>
        </div>
      )}
      {data && (
        <>
          <Current forecast={data} units={units} />
          <ForecastTimeline forecast={data} units={units} />
          <Hourly forecast={data} units={units} />
          <Daily forecast={data} units={units} />
          <div className={styles.mediaCaption}>
            Forecast for the nearest model grid point, in the place&apos;s local time. Data:{' '}
            <a className={styles.sourceLink} href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
              Open-Meteo
            </a>{' '}
            (CC BY 4.0).
          </div>
        </>
      )}
    </div>
  );
}
