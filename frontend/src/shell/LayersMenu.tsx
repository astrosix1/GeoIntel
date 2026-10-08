import PremiumGate from '../components/PremiumGate';
import { WEATHER_FIELDS } from '../globe/weatherLayers';
import { useUiStore } from '../state/uiStore';
import { Popover } from '../ui/Overlay';
import styles from './Menus.module.css';

function SwitchRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className={styles.switch}>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

// Everything that is an overlay on the map, in one place (it used to be spread over four floating groups). Satellite
// and Topography are premium; the radar belongs to Weather mode and the night side and zone labels to Time Zone mode,
// so each mode shows only the layers that mean something there.
export default function LayersMenu() {
  const mode = useUiStore((s) => s.activeMode);
  const satellite = useUiStore((s) => s.satellite);
  const relief = useUiStore((s) => s.relief);
  const setSatellite = useUiStore((s) => s.setSatellite);
  const setRelief = useUiStore((s) => s.setRelief);
  const radarOn = useUiStore((s) => s.radarOn);
  const setRadarOn = useUiStore((s) => s.setRadarOn);
  const field = useUiStore((s) => s.weatherField);
  const setField = useUiStore((s) => s.setWeatherField);
  const cloudsOn = useUiStore((s) => s.cloudsOn);
  const setCloudsOn = useUiStore((s) => s.setCloudsOn);
  const firesOn = useUiStore((s) => s.firesOn);
  const setFiresOn = useUiStore((s) => s.setFiresOn);
  const nightOn = useUiStore((s) => s.nightOn);
  const setNightOn = useUiStore((s) => s.setNightOn);
  const labelsOn = useUiStore((s) => s.zoneLabelsOn);
  const setLabelsOn = useUiStore((s) => s.setZoneLabelsOn);

  return (
    <Popover label="Layers" icon="layers" align="end">
      <div className={styles.menu}>
        <div>
          <span className={styles.groupTitle}>Base map</span>
          <PremiumGate feature="Satellite view" block>
            <SwitchRow label="Satellite" checked={satellite} onChange={setSatellite} />
          </PremiumGate>
          <PremiumGate feature="Topography" block>
            <SwitchRow label="Topography" checked={relief} onChange={setRelief} />
          </PremiumGate>
        </div>
        {mode === 'weather' && (
          <div>
            <span className={styles.groupTitle}>Weather</span>
            <SwitchRow label="Radar, live (loops the past 2 hours)" checked={radarOn} onChange={setRadarOn} />
            <SwitchRow label="Clouds (live infrared; Americas, Pacific, East Asia, Australia)" checked={cloudsOn} onChange={setCloudsOn} />
            <SwitchRow label="Fires (satellite detections today)" checked={firesOn} onChange={setFiresOn} />
          </div>
        )}
        {mode === 'weather' && (
          <div role="radiogroup" aria-label="Forecast map">
            <span className={styles.groupTitle}>Forecast map (model, not observed)</span>
            <span className={styles.hint}>The live radar looks back, not ahead. For rain ahead, use the rain forecast.</span>
            <label className={styles.switch}>
              <input type="radio" name="forecast-field" checked={field === null} onChange={() => setField(null)} />
              <span>None</span>
            </label>
            {WEATHER_FIELDS.map((f) => (
              <label key={f.key} className={styles.switch}>
                <input type="radio" name="forecast-field" checked={field === f.key} onChange={() => setField(f.key)} />
                <span>{f.label}</span>
              </label>
            ))}
          </div>
        )}
        {mode === 'timezone' && (
          <div>
            <span className={styles.groupTitle}>Time</span>
            <SwitchRow label="Night side" checked={nightOn} onChange={setNightOn} />
            <SwitchRow label="Zone time labels" checked={labelsOn} onChange={setLabelsOn} />
          </div>
        )}
      </div>
    </Popover>
  );
}
