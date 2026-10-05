import { useState } from 'react';
import { isLiteDevice } from '../lite';
import { useUiStore } from '../state/uiStore';
import styles from './MapLegend.module.css';

// Key to how Events-mode pins are drawn. Collapsed by default on phones, where
// space is tight.
export default function MapLegend() {
  const activeMode = useUiStore((s) => s.activeMode);
  const [open, setOpen] = useState(() => !isLiteDevice());

  if (activeMode !== 'events') return null;

  return (
    <div className={styles.legend} data-ui-hover-surface>
      <button type="button" className={styles.toggle} aria-expanded={open} onClick={() => setOpen(!open)}>
        Key {open ? '▾' : '▸'}
      </button>
      {open && (
        <ul className={styles.list}>
          <li>
            <span className={`${styles.swatch} ${styles.solid}`} aria-hidden="true" />
            Something that happened
          </li>
          <li>
            <span className={`${styles.swatch} ${styles.hollow}`} aria-hidden="true" />
            A statement or talks (no physical place)
          </li>
          <li>
            <span className={`${styles.swatch} ${styles.ring}`} aria-hidden="true" />
            Ring: approximate area (wider = less precise)
          </li>
        </ul>
      )}
    </div>
  );
}
