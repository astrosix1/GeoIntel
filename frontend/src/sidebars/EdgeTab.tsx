import { useUiStore } from '../state/uiStore';
import styles from './EdgeTab.module.css';

interface EdgeTabProps {
  side: 'left' | 'right';
}

// Phase 10.3: a small, always-visible pull-tab fixed to the screen edge,
// replacing the old invisible 10%-of-viewport hover zone. Hovering it opens
// the corresponding sidebar (via useHoverZone.ts); a plain click toggles it
// open too, for accessibility beyond pure hover. Marked
// data-ui-hover-surface so hovering the tab itself is never mistaken for
// "hovering the globe" (which force-closes both sidebars).
export default function EdgeTab({ side }: EdgeTabProps) {
  const setLeftEdgeHovered = useUiStore((s) => s.setLeftEdgeHovered);
  const setRightEdgeHovered = useUiStore((s) => s.setRightEdgeHovered);
  const toggleLeftManual = useUiStore((s) => s.toggleLeftManual);
  const toggleRightManual = useUiStore((s) => s.toggleRightManual);
  const leftOpen = useUiStore((s) => s.leftOpen);
  const rightOpen = useUiStore((s) => s.rightOpen);

  const isOpen = side === 'left' ? leftOpen : rightOpen;
  const setHovered = side === 'left' ? setLeftEdgeHovered : setRightEdgeHovered;
  const toggleManual = side === 'left' ? toggleLeftManual : toggleRightManual;

  return (
    <button
      type="button"
      data-ui-hover-surface
      className={`${styles.tab} ${styles[side]} ${isOpen ? styles.open : ''}`}
      aria-label={side === 'left' ? 'Toggle Events sidebar' : 'Toggle Analysis sidebar'}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={toggleManual}
    >
      <span className={styles.chevron} aria-hidden="true">
        {side === 'left' ? (isOpen ? '‹' : '›') : isOpen ? '›' : '‹'}
      </span>
    </button>
  );
}
