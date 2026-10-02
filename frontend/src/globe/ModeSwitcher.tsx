import { useUiStore } from '../state/uiStore';
import type { GlobeMode } from '../state/uiStore';
import PremiumGate from '../components/PremiumGate';
import styles from './ModeSwitcher.module.css';

// Persistent globe-mode control (step 5 of the rewrite plan). Placed near
// the top-center of the screen — there's no logo yet to sit next to, and
// this keeps it clear of MapLibre's own NavigationControl in the top-right.
// Switching modes never closes a sidebar or clears the pinned Analysis
// selection (see uiStore.setActiveMode) — it only changes what Globe.tsx
// renders on the map itself.
const MODES: { value: GlobeMode; label: string }[] = [
  { value: 'events', label: 'Events' },
  { value: 'weather', label: 'Weather' },
  { value: 'timezone', label: 'Time Zone' },
];

export default function ModeSwitcher() {
  const activeMode = useUiStore((s) => s.activeMode);
  const setActiveMode = useUiStore((s) => s.setActiveMode);

  return (
    <div className={styles.switcher} data-ui-hover-surface>
      {MODES.map((mode) => (
        <button
          key={mode.value}
          type="button"
          className={`${styles.option} ${activeMode === mode.value ? styles.optionActive : ''}`}
          onClick={() => setActiveMode(mode.value)}
        >
          {mode.label}
        </button>
      ))}
      {/* First premium feature slot. The satellite/topography layers aren't
          built yet, so this is a disabled placeholder for premium members
          and a locked, prompt-showing control for everyone else. */}
      <PremiumGate feature="Satellite view">
        <button type="button" className={styles.option} disabled title="Coming soon">
          Satellite
        </button>
      </PremiumGate>
    </div>
  );
}
