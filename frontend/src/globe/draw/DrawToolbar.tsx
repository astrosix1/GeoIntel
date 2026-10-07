import { useDrawStore } from '../../state/drawStore';
import { IconButton } from '../../ui/Button';
import type { IconName } from '../../ui/Icon';
import { drawController } from './controller';
import type { DrawTool } from './engine';
import styles from './DrawToolbar.module.css';

const TOOLS: { tool: DrawTool; icon: IconName; label: string; hint: string }[] = [
  { tool: 'select', icon: 'pointer', label: 'Select and edit', hint: 'Click a shape to select it; drag to move it or its corners.' },
  { tool: 'point', icon: 'dot', label: 'Point', hint: 'Click to drop a point.' },
  { tool: 'linestring', icon: 'line', label: 'Line (measure a distance)', hint: 'Click to add corners; click the last corner again, or press Enter, to finish.' },
  { tool: 'polygon', icon: 'polygon', label: 'Area (measure an area)', hint: 'Click to add corners; click the first corner, or press Enter, to finish.' },
  { tool: 'rectangle', icon: 'rectangle', label: 'Rectangle', hint: 'Click and drag, or click two opposite corners.' },
  { tool: 'circle', icon: 'circle', label: 'Circle (by radius)', hint: 'Click the centre, then click or drag out to the edge.' },
  { tool: 'freehand', icon: 'freehand', label: 'Freehand', hint: 'Press and drag to draw; let go to finish.' },
];

// The drawing tool strip over the map: pick a tool, undo and redo, delete the selected shape. It is built from the same
// buttons as the rest of the app, so it follows the theme and has 44 px targets on touch.
export default function DrawToolbar() {
  const open = useDrawStore((s) => s.open);
  const tool = useDrawStore((s) => s.tool);
  const setTool = useDrawStore((s) => s.setTool);
  const setOpen = useDrawStore((s) => s.setOpen);
  const canUndo = useDrawStore((s) => s.canUndo);
  const canRedo = useDrawStore((s) => s.canRedo);
  const selectedId = useDrawStore((s) => s.selectedId);
  const shapeCount = useDrawStore((s) => s.shapeCount);
  if (!open) return null;

  const active = TOOLS.find((t) => t.tool === tool);

  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Drawing tools" data-ui-hover-surface>
      {TOOLS.map((t) => (
        <IconButton
          key={t.tool}
          icon={t.icon}
          label={t.label}
          variant={tool === t.tool ? 'primary' : 'quiet'}
          aria-pressed={tool === t.tool}
          onClick={() => setTool(t.tool)}
        />
      ))}
      <div className={styles.divider} />
      <IconButton icon="undo" label="Undo (Ctrl+Z)" disabled={!canUndo} onClick={() => drawController.undo()} />
      <IconButton icon="redo" label="Redo (Ctrl+Y)" disabled={!canRedo} onClick={() => drawController.redo()} />
      <IconButton icon="trash" label="Delete the selected shape" disabled={selectedId === null} onClick={() => drawController.deleteSelected()} />
      <IconButton icon="close" label="Clear everything" disabled={shapeCount === 0} onClick={() => drawController.clear()} />
      <div className={styles.divider} />
      <IconButton icon="check" label="Done: hide the drawing tools (the drawing stays on the map)" onClick={() => setOpen(false)} />
      {active && <div className={styles.status}>{active.hint}</div>}
    </div>
  );
}
