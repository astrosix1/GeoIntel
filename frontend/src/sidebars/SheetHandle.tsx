import { IconButton } from '../ui/Button';
import styles from './SheetHandle.module.css';

// The top row of a panel when it is a bottom sheet on a phone: a grab bar (tap to switch between half and full height)
// and a close button. Hidden on wide screens, where panels are columns or side drawers.
export default function SheetHandle({ full, onToggle, onClose }: { full: boolean; onToggle: () => void; onClose: () => void }) {
  return (
    <div className={styles.row}>
      <button type="button" className={styles.handle} aria-label={full ? 'Make the panel smaller' : 'Make the panel taller'} onClick={onToggle}>
        <span className={styles.bar} />
      </button>
      <IconButton icon="close" label="Close panel" className={styles.close} onClick={onClose} />
    </div>
  );
}
