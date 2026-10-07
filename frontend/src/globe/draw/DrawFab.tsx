import { useDrawStore } from '../../state/drawStore';
import Button from '../../ui/Button';
import styles from './DrawFab.module.css';

// On phones the Draw button sits at the bottom centre of the map (the top bar has no room for it).
export default function DrawFab() {
  const open = useDrawStore((s) => s.open);
  const setOpen = useDrawStore((s) => s.setOpen);
  return (
    <div className={styles.fab} data-ui-hover-surface>
      <Button icon="pencil" variant={open ? 'primary' : 'default'} aria-pressed={open} onClick={() => setOpen(!open)}>
        Draw
      </Button>
    </div>
  );
}
