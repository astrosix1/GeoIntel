import PremiumGate from '../components/PremiumGate';
import { radarCanAnimate } from '../globe/useRadar';
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
  const radarPlaying = useUiStore((s) => s.radarPlaying);
  const setRadarPlaying = useUiStore((s) => s.setRadarPlaying);
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
            <SwitchRow label="Radar (past 2 hours)" checked={radarOn} onChange={setRadarOn} />
            {radarOn && radarCanAnimate() && <SwitchRow label="Play the radar loop" checked={radarPlaying} onChange={setRadarPlaying} />}
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
