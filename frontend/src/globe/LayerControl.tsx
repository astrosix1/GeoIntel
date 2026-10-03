import { useUiStore } from '../state/uiStore';
import PremiumGate from '../components/PremiumGate';
import styles from './LayerControl.module.css';

// Premium globe layers, under MapLibre's zoom control. They slide left of the
// Analysis panel while it's open (and hide on phones, where it covers nearly
// the whole screen) so they never sit on top of its content. Each toggle is gated
// individually: non-premium visitors see it dimmed with a lock and the right
// prompt. (Globe.tsx also requires premium before rendering a layer.)
export default function LayerControl() {
  const satellite = useUiStore((s) => s.satellite);
  const relief = useUiStore((s) => s.relief);
  const setSatellite = useUiStore((s) => s.setSatellite);
  const setRelief = useUiStore((s) => s.setRelief);
  const analysisOpen = useUiStore((s) => s.rightOpen);

  return (
    <div className={`${styles.stack} ${analysisOpen ? styles.beside : ''}`} data-ui-hover-surface>
      <PremiumGate feature="Satellite view">
        <button
          type="button"
          aria-pressed={satellite}
          className={`${styles.toggle} ${satellite ? styles.active : ''}`}
          onClick={() => setSatellite(!satellite)}
        >
          Satellite
        </button>
      </PremiumGate>
      <PremiumGate feature="Topography">
        <button
          type="button"
          aria-pressed={relief}
          className={`${styles.toggle} ${relief ? styles.active : ''}`}
          onClick={() => setRelief(!relief)}
        >
          Topography
        </button>
      </PremiumGate>
    </div>
  );
}
