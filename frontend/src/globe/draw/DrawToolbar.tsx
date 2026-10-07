import { useState } from 'react';
import { useDrawStore } from '../../state/drawStore';
import { IconButton } from '../../ui/Button';
import type { IconName } from '../../ui/Icon';
import Segmented from '../../ui/Segmented';
import { drawController } from './controller';
import type { DrawTool } from './engine';
import type { DrawUnits } from './prefs';
import { imageFileName } from './imagetext';
import { DEFAULT_NAME } from './draft';
import { startPresenting } from './present';
import DrawingsPanel from './DrawingsPanel';
import LayersPanel from './LayersPanel';
import ShapePanel from './ShapePanel';
import styles from './DrawToolbar.module.css';

const TOOLS: { tool: DrawTool; icon: IconName; label: string; hint: string }[] = [
  { tool: 'select', icon: 'pointer', label: 'Select and edit', hint: 'Click a shape to select it; drag to move it or its corners.' },
  { tool: 'point', icon: 'dot', label: 'Point (shows its coordinates)', hint: 'Click to drop a point.' },
  { tool: 'text', icon: 'text', label: 'Text (add words to the map)', hint: 'Click where the words go, then type them in the panel.' },
  { tool: 'linestring', icon: 'line', label: 'Line (measure a distance)', hint: 'Click to add corners; click the last corner again, or press Enter, to finish.' },
  { tool: 'arrow', icon: 'arrow', label: 'Arrow (shows its length and bearing)', hint: 'Click the start, then click the tip.' },
  { tool: 'angle', icon: 'angle', label: 'Angle (measure an angle)', hint: 'Click the end of one leg, then the corner, then the end of the other leg.' },
  { tool: 'polygon', icon: 'polygon', label: 'Area (measure an area)', hint: 'Click to add corners; click the first corner, or press Enter, to finish.' },
  { tool: 'rectangle', icon: 'rectangle', label: 'Rectangle', hint: 'Click and drag, or click two opposite corners.' },
  { tool: 'circle', icon: 'circle', label: 'Circle (shows its radius)', hint: 'Click the centre, then click or drag out to the edge.' },
  { tool: 'freehand', icon: 'freehand', label: 'Freehand', hint: 'Press and drag to draw; let go to finish.' },
];

const UNIT_OPTIONS: { value: DrawUnits; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'metric', label: 'Metric' },
  { value: 'imperial', label: 'Imperial' },
  { value: 'nautical', label: 'Nautical' },
];

// What the tool measures and shows on the map: the units, and the extra figures (every segment, every corner angle,
// compass bearings). The total length or area of a shape is always shown.
function MeasureOptions() {
  const prefs = useDrawStore((s) => s.prefs);
  const setPrefs = useDrawStore((s) => s.setPrefs);
  return (
    <div className={styles.options} role="group" aria-label="Measuring options">
      <div className={styles.optionRow}>
        <span className={styles.optionLabel}>Units</span>
        <Segmented label="Measuring units" size="sm" value={prefs.units} onChange={(units) => setPrefs({ units })} options={UNIT_OPTIONS} />
      </div>
      <label className={styles.switch}>
        <input type="checkbox" role="switch" checked={prefs.segments} onChange={(e) => setPrefs({ segments: e.target.checked })} />
        <span>Length of each side</span>
      </label>
      <label className={styles.switch}>
        <input type="checkbox" role="switch" checked={prefs.angles} onChange={(e) => setPrefs({ angles: e.target.checked })} />
        <span>Angle at each corner</span>
      </label>
      <label className={styles.switch}>
        <input type="checkbox" role="switch" checked={prefs.bearings} onChange={(e) => setPrefs({ bearings: e.target.checked })} />
        <span>Compass bearing of each side</span>
      </label>
      <p className={styles.optionHint}>Angles are the smaller angle between two sides (0 to 180°). Bearings are degrees clockwise from north.</p>
    </div>
  );
}

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
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [drawingsOpen, setDrawingsOpen] = useState(false);
  const dirty = useDrawStore((s) => s.dirty);
  const presenting = useDrawStore((s) => s.presenting);
  const drawingName = useDrawStore((s) => s.drawing.name);
  const [imageNote, setImageNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  if (!open || presenting) return null;

  async function saveImage() {
    setSaving(true);
    setImageNote(null);
    const blob = await drawController.captureImage(drawingName === DEFAULT_NAME ? null : drawingName);
    setSaving(false);
    if (!blob) {
      setImageNote('The image could not be saved. Try again.');
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = imageFileName(drawingName);
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Not at once: some browsers are still starting the download.
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    setImageNote('Image saved.');
  }

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
      <IconButton
        icon="save"
        label={dirty ? 'Drawings: save, open, export (unsaved changes)' : 'Drawings: save, open, export'}
        variant={drawingsOpen ? 'primary' : 'quiet'}
        aria-pressed={drawingsOpen}
        aria-expanded={drawingsOpen}
        onClick={() => setDrawingsOpen(!drawingsOpen)}
      />
      <IconButton
        icon="layers"
        label="Layers: group shapes into scenarios"
        variant={layersOpen ? 'primary' : 'quiet'}
        aria-pressed={layersOpen}
        aria-expanded={layersOpen}
        onClick={() => setLayersOpen(!layersOpen)}
      />
      <IconButton
        icon="ruler"
        label="Measuring options: units, sides, angles, bearings"
        variant={optionsOpen ? 'primary' : 'quiet'}
        aria-pressed={optionsOpen}
        aria-expanded={optionsOpen}
        onClick={() => setOptionsOpen(!optionsOpen)}
      />
      <IconButton
        icon="camera"
        label="Save the view as an image (PNG)"
        disabled={saving}
        onClick={() => void saveImage()}
      />
      <IconButton icon="present" label="Presentation mode: hide everything but the map (Escape leaves)" onClick={startPresenting} />
      <IconButton icon="check" label="Done: hide the drawing tools (the drawing stays on the map)" onClick={() => setOpen(false)} />
      {active && <div className={styles.status}>{active.hint}</div>}
      {imageNote && (
        <div className={styles.status} role="status">
          {imageNote}
        </div>
      )}
      <div className={styles.side}>
        {drawingsOpen && <DrawingsPanel />}
        {layersOpen && <LayersPanel />}
        <ShapePanel />
        {optionsOpen && <MeasureOptions />}
      </div>
    </div>
  );
}
