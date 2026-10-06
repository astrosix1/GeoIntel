import { useUiStore } from '../state/uiStore';
import styles from './EdgeTab.module.css';

interface EdgeTabProps {
  side: 'left' | 'right';
  // Docked: the tab sits on the map's own edge and only collapses or restores the panel (no opening on hover).
  docked?: boolean;
}

// A small, always-visible pull-tab fixed to the screen edge. Hovering it
// opens the corresponding sidebar; once open, the tab itself becomes an
// explicit close (×) button instead of the sidebar auto-closing when the
// cursor moves elsewhere (e.g. onto the globe) — confirmed with you that
// the previous auto-close-on-hover-away behavior was unwanted. Marked
// data-ui-hover-surface, left over from the old globe-hover-closes-
// everything listener; harmless now that nothing reads it to force-close.
export default function EdgeTab({ side, docked = false }: EdgeTabProps) {
  const setLeftOpen = useUiStore((s) => s.setLeftOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const leftOpen = useUiStore((s) => s.leftOpen);
  const rightOpen = useUiStore((s) => s.rightOpen);

  const isOpen = side === 'left' ? leftOpen : rightOpen;
  const setOpen = side === 'left' ? setLeftOpen : setRightOpen;

  return (
    <button
      type="button"
      data-ui-hover-surface
      className={`${styles.tab} ${styles[side]} ${isOpen ? styles.open : ''} ${docked ? styles.inMap : ''}`}
      aria-label={
        isOpen
          ? side === 'left' ? 'Close Events sidebar' : 'Close Analysis sidebar'
          : side === 'left' ? 'Open Events sidebar' : 'Open Analysis sidebar'
      }
      onMouseEnter={docked ? undefined : () => setOpen(true)}
      onClick={() => setOpen(!isOpen)}
    >
      <span className={styles.chevron} aria-hidden="true">
        {docked ? ((side === 'left') === isOpen ? '‹' : '›') : isOpen ? '×' : side === 'left' ? '›' : '‹'}
      </span>
    </button>
  );
}
