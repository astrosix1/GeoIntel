import { useQueries } from '@tanstack/react-query';
import { fetchForecast } from '../../api/client';
import type { Forecast, Storm } from '../../api/types';
import { distanceKm } from '../../lib/geo';
import { formatRain, formatSpeed, formatTemp } from '../../lib/units';
import type { UnitSystem } from '../../lib/units';
import { describeWeather } from '../../lib/weatherCodes';
import { useStormsQuery } from '../../state/queries';
import { useUiStore } from '../../state/uiStore';
import styles from './EventAnalysis.module.css';
import forecastStyles from './PointForecast.module.css';

// A hazard counts as "near" when its pin is within this distance of the place. This is the
// pin's position, not the hazard's footprint, and the panel says so.
export const NEAR_HAZARD_KM = 300;

function sum(values: (number | null | undefined)[] | undefined): number | null {
  if (!values || values.length === 0) return null;
  return values.reduce<number>((total, v) => total + (typeof v === 'number' ? v : 0), 0);
}

function peak(values: (number | null | undefined)[] | undefined): number | null {
  const numbers = (values ?? []).filter((v): v is number => typeof v === 'number');
  return numbers.length ? Math.max(...numbers) : null;
}

function nearHazards(storms: Storm[], lat: number, lon: number): { storm: Storm; km: number }[] {
  return storms
    .filter((s) => typeof s.lat === 'number' && typeof s.lon === 'number')
    .map((storm) => ({ storm, km: distanceKm(lat, lon, storm.lat as number, storm.lon as number) }))
    .filter((x) => x.km <= NEAR_HAZARD_KM)
    .sort((a, b) => a.km - b.km);
}

function Cell({ forecast, units }: { forecast: Forecast; units: UnitSystem }) {
  const d = forecast.daily;
  const sky = describeWeather(forecast.current.weather_code);
  return (
    <>
      <td>
        <span aria-hidden="true">{sky.icon}</span> {formatTemp(forecast.current.temperature_2m, units)}
      </td>
      <td>
        {formatTemp(d.temperature_2m_max?.[0], units)}
        <span className={forecastStyles.low}> / {formatTemp(d.temperature_2m_min?.[0], units)}</span>
      </td>
      <td>{formatRain(sum(d.precipitation_sum), units)}</td>
      <td>{peak(d.wind_gusts_10m_max) != null ? formatSpeed(peak(d.wind_gusts_10m_max), units) : '–'}</td>
    </>
  );
}

// Up to three places side by side: now, today's high/low, 7-day rain and the strongest gust
// in the next 7 days, plus any hazard whose pin is within NEAR_HAZARD_KM. Each place loads
// on its own, so one failing place never hides the others.
export default function ComparePlaces({ units }: { units: UnitSystem }) {
  const places = useUiStore((s) => s.comparePlaces);
  const removePlace = useUiStore((s) => s.removeComparePlace);
  const clearPlaces = useUiStore((s) => s.clearComparePlaces);
  const { data: stormData } = useStormsQuery(true);
  const results = useQueries({
    queries: places.map((p) => ({
      queryKey: ['forecast', p.lat, p.lon],
      queryFn: () => fetchForecast(p.lat, p.lon),
      retry: false,
      staleTime: 15 * 60 * 1000,
      refetchOnWindowFocus: false,
    })),
  });
  const attribution = results.find((r) => r.data?.attribution)?.data?.attribution;
  if (places.length === 0) return null;

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>
        Compare places ({places.length}/3){' '}
        <button type="button" className={forecastStyles.retry} onClick={clearPlaces}>
          Clear
        </button>
      </div>
      <table className={forecastStyles.days}>
        <thead>
          <tr>
            <th scope="col">Place</th>
            <th scope="col">Now</th>
            <th scope="col">Today</th>
            <th scope="col">7-day rain</th>
            <th scope="col">Top gust</th>
          </tr>
        </thead>
        <tbody>
          {places.map((place, i) => {
            const result = results[i];
            const hazards = stormData ? nearHazards(stormData.storms, place.lat, place.lon) : [];
            return (
              <tr key={`${place.lat},${place.lon}`}>
                <td>
                  {place.label}{' '}
                  <button
                    type="button"
                    className={forecastStyles.retry}
                    aria-label={`Remove ${place.label}`}
                    onClick={() => removePlace(place.lat, place.lon)}
                  >
                    ×
                  </button>
                  {hazards.length > 0 && (
                    <div className={forecastStyles.low}>
                      {hazards.length} hazard{hazards.length === 1 ? '' : 's'} within {NEAR_HAZARD_KM} km:{' '}
                      {hazards
                        .slice(0, 2)
                        .map(({ storm, km }) => `${storm.name ?? storm.hazard ?? 'hazard'} (${Math.round(km)} km)`)
                        .join(', ')}
                    </div>
                  )}
                </td>
                {result.data ? (
                  <Cell forecast={result.data} units={units} />
                ) : (
                  <td colSpan={4}>{result.isError ? 'Forecast unavailable' : 'Loading…'}</td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className={styles.mediaCaption}>
        Hazards are listed by their pin&apos;s distance from the place, not their full footprint. Forecast data:{' '}
        {attribution ? (
          <a className={styles.sourceLink} href={attribution.url} target="_blank" rel="noopener noreferrer">{attribution.name}</a>
        ) : (
          'MET Norway'
        )}{' '}
        ({attribution?.license ?? 'CC BY 4.0 / NLOD 2.0'}).
      </div>
    </div>
  );
}
