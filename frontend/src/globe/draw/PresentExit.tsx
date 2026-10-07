import { useDrawStore } from '../../state/drawStore';
import Button from '../../ui/Button';
import { stopPresenting } from './present';
import styles from './PresentExit.module.css';

// The one control left on screen in presentation mode, kept faint so it does not get in the way of the slide.
export default function PresentExit() {
  const presenting = useDrawStore((s) => s.presenting);
  if (!presenting) return null;
  return (
    <div className={styles.exit} data-ui-hover-surface>
      <Button size="sm" icon="close" onClick={stopPresenting} aria-label="Exit presentation mode (Escape)">
        Exit presentation
      </Button>
    </div>
  );
}
