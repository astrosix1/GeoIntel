import { useState } from 'react';
import { useDrawStore } from '../state/drawStore';
import { useWeatherLayersQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import styles from './WeatherLayers.module.css';
import { fieldLegendUrl } from './weatherLayers';

// The colour key for the forecast map layer: DWD's own legend picture, titled with what the layer shows and labelled as a forecast.
export default function WeatherFieldLegend() {
  const mode = useUiStore((s) => s.activeMode);
  const field = useUiStore((s) => s.weatherField);
  const presenting = useDrawStore((s) => s.presenting);
  const { data } = useWeatherLayersQuery(mode === 'weather' && field !== null);
  const layer = field && data ? data.layers[field] : undefined;
  const [failed, setFailed] = useState<string | null>(null);
  if (presenting || mode !== 'weather' || !layer) return null;
  return (
    <div className={styles.legend} data-ui-hover-surface>
      <span className={styles.legendTitle}>{layer.label}</span>
      <span className={styles.legendNote}>{field === 'radar' ? 'Forecast (DWD radar nowcast)' : 'Forecast (DWD ICON model)'}</span>
      {field === 'radar' && <span className={styles.legendNote}>Germany and its surroundings only; elsewhere the map is untouched. Grey shading is outside the radars&apos; range.</span>}
      {field === 'wind' || failed === layer.wms_layer ? (
        <span className={styles.legendNote}>
          {field === 'wind'
            ? 'Wind barbs: the staff points to where the wind comes from. A short tick is 5 knots, a long tick 10, a flag 50.'
            : 'No colour key is published for this layer.'}
        </span>
      ) : (
        <img
          className={styles.legendImage}
          src={fieldLegendUrl(layer.wms_layer)}
          alt={`Colour key for ${layer.label}`}
          loading="lazy"
          onError={() => setFailed(layer.wms_layer)}
        />
      )}
    </div>
  );
}
