import { useDrawStore } from '../state/drawStore';
import { useUiStore } from '../state/uiStore';
import { EXPOSURE_COLORS } from './cascadeLayer';
import styles from './CascadeLegend.module.css';

// The colour key for the cascade on the map, with the way back to the result and a way to clear it.
export default function CascadeLegend() {
  const result = useUiStore((s) => s.cascadeResult);
  const setResult = useUiStore((s) => s.setCascadeResult);
  const setOpen = useUiStore((s) => s.setCascadeOpen);
  const presenting = useDrawStore((s) => s.presenting);
  const inEvents = useUiStore((s) => s.activeMode) === 'events';
  if (!result || presenting || !inEvents) return null;
  const t = result.trigger;
  return (
    <div className={styles.legend} data-ui-hover-surface>
      <span className={styles.title}>
        Cascade: {t.label.toLowerCase()}, {t.country_name}
        {t.commodity_label ? `, ${t.commodity_label.toLowerCase()}` : ''}
      </span>
      <ul className={styles.keys}>
        {(['Trigger', 'High', 'Moderate', 'Low'] as const).map((k) => (
          <li key={k}>
            <span className={styles.swatch} style={{ background: EXPOSURE_COLORS[k] }} />
            {k === 'Trigger' ? 'Where it happens' : `${k} exposure`}
          </li>
        ))}
      </ul>
      <span className={styles.actions}>
        <button type="button" className={styles.link} onClick={() => setOpen(true)}>
          Open result
        </button>
        <button type="button" className={styles.link} onClick={() => setResult(null)}>
          Clear
        </button>
      </span>
    </div>
  );
}
