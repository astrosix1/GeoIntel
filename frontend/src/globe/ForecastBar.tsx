import { useDrawStore } from '../state/drawStore';
import { useWeatherLayersQuery } from '../state/queries';
import { useNow } from '../state/useNow';
import { useUiStore } from '../state/uiStore';
import Button from '../ui/Button';
import radarStyles from './TimeBar.module.css';
import styles from './WeatherLayers.module.css';
import { formatForecastTime, nearestTime, relativeHours } from './weatherLayers';

// The forecast timeline for the forecast map layer: drag to any hour the model has, or press Now. It says plainly that this is a
// model forecast, not an observation. Sits above the radar timeline when both are showing.
export default function ForecastBar() {
  const mode = useUiStore((s) => s.activeMode);
  const field = useUiStore((s) => s.weatherField);
  const forecastTime = useUiStore((s) => s.forecastTime);
  const setForecastTime = useUiStore((s) => s.setForecastTime);
  const radarVisible = useUiStore((s) => s.radarOn && s.radarFrameTimes.length > 0);
  const presenting = useDrawStore((s) => s.presenting);
  const now = useNow(60_000).getTime();
  const { data, isError, isLoading } = useWeatherLayersQuery(mode === 'weather' && field !== null);
  if (presenting || mode !== 'weather' || !field) return null;

  const lift = radarVisible ? styles.lifted : '';
  if (isError) {
    return (
      <div className={`${radarStyles.bar} ${lift}`} role="status" data-ui-hover-surface>
        <div className={radarStyles.readout}>The forecast map layers aren&apos;t available right now.</div>
      </div>
    );
  }
  const times = data?.layers[field]?.times;
  if (isLoading || !times || times.length === 0) return null;

  const current = nearestTime(times, forecastTime ?? now) as string;
  const index = Math.max(0, times.indexOf(current));
  const isNow = forecastTime === null;

  return (
    <div className={`${radarStyles.bar} ${lift}`} data-ui-hover-surface>
      <div className={radarStyles.middle}>
        <input
          className={radarStyles.slider}
          type="range"
          min={0}
          max={times.length - 1}
          step={1}
          value={index}
          onChange={(e) => setForecastTime(Date.parse(times[Number(e.target.value)]))}
          aria-label="Choose a forecast hour for the map"
          aria-valuetext={`${formatForecastTime(current)}, ${relativeHours(current, now)}`}
        />
        <div className={`${radarStyles.readout} ${isNow ? '' : radarStyles.shifted}`}>
          Forecast for {formatForecastTime(current)} · {relativeHours(current, now)} · model, not observed
        </div>
      </div>
      <Button size="sm" disabled={isNow} onClick={() => setForecastTime(null)}>
        Now
      </Button>
    </div>
  );
}
