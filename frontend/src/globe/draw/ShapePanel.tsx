import { useState } from 'react';
import { useDrawStore } from '../../state/drawStore';
import Button from '../../ui/Button';
import Segmented from '../../ui/Segmented';
import { drawController } from './controller';
import { colorOf, dashOf, FILLS, fillOf, MAX_LABEL_LENGTH, MAX_NOTE_LENGTH, PALETTE, WIDTHS, widthOf } from './style';
import type { Dash } from './style';
import styles from './ShapePanel.module.css';

// Name and note fields keep their own text while it is being typed and hand it to the drawing when the field is left (or
// Enter is pressed), so one edit is one step in the undo history rather than one per keystroke.
function TextFields({ initialName, initialNote, isText }: { initialName: string; initialNote: string; isText: boolean }) {
  const [name, setName] = useState(initialName);
  const [note, setNote] = useState(initialNote);
  return (
    <>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{isText ? 'Text' : 'Name (shown on the map)'}</span>
        <input
          className={styles.input}
          value={name}
          maxLength={MAX_LABEL_LENGTH}
          placeholder={isText ? 'Type the words' : 'Optional'}
          autoFocus={isText}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => drawController.setStyle({ label: name })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') drawController.setStyle({ label: name });
          }}
        />
      </label>
      {!isText && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Note</span>
          <textarea
            className={styles.textarea}
            value={note}
            maxLength={MAX_NOTE_LENGTH}
            rows={3}
            placeholder="Optional: what this shape means"
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => drawController.setStyle({ note })}
          />
        </label>
      )}
    </>
  );
}

// The panel for the selected shape: its name and note, colour, line width, fill and dashes, and Duplicate and Delete.
export default function ShapePanel() {
  const selectedId = useDrawStore((s) => s.selectedId);
  const layers = useDrawStore((s) => s.layers);
  useDrawStore((s) => s.revision); // read the shape again after every change
  const [duplicateFailed, setDuplicateFailed] = useState(false);
  const feature = selectedId === null ? null : drawController.selected();
  if (!feature) return null;

  const props = feature.properties ?? {};
  const mode = String(props.mode ?? '');
  const geometry = feature.geometry.type;
  const isText = mode === 'text';
  const hasLine = geometry === 'LineString' || geometry === 'Polygon';
  const color = colorOf(props);

  return (
    <div className={styles.panel} role="group" aria-label="Selected shape">
      <TextFields key={`${selectedId}:${mode}`} initialName={typeof props.label === 'string' ? props.label : ''} initialNote={typeof props.note === 'string' ? props.note : ''} isText={isText} />

      <div className={styles.field}>
        <span className={styles.fieldLabel}>Colour</span>
        <div className={styles.swatches} role="group" aria-label="Colour">
          {PALETTE.map((c) => (
            <button
              key={c.value}
              type="button"
              className={`${styles.swatch} ${color === c.value ? styles.swatchOn : ''}`}
              style={{ background: c.value }}
              aria-label={c.label}
              aria-pressed={color === c.value}
              title={c.label}
              onClick={() => drawController.setStyle({ color: c.value })}
            />
          ))}
        </div>
      </div>

      {hasLine && !isText && (
        <div className={styles.field}>
          <span className={styles.fieldLabel}>{geometry === 'Polygon' ? 'Outline' : 'Line'}</span>
          <Segmented
            label="Line width"
            size="sm"
            value={String(widthOf(props))}
            onChange={(v) => drawController.setStyle({ width: Number(v) })}
            options={WIDTHS.map((w) => ({ value: String(w.value), label: w.label }))}
          />
        </div>
      )}
      {geometry === 'Polygon' && (
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Fill</span>
          <Segmented
            label="Fill"
            size="sm"
            value={String(fillOf(props))}
            onChange={(v) => drawController.setStyle({ fill: Number(v) })}
            options={FILLS.map((f) => ({ value: String(f.value), label: f.label }))}
          />
        </div>
      )}
      {geometry === 'LineString' && (
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Pattern</span>
          <Segmented
            label="Line pattern"
            size="sm"
            value={(dashOf(props) ? 'dashed' : 'solid') as Dash}
            onChange={(dash) => drawController.setStyle({ dash })}
            options={[{ value: 'solid', label: 'Solid' }, { value: 'dashed', label: 'Dashed' }]}
          />
        </div>
      )}

      {layers.length > 1 && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Layer</span>
          <select
            className={styles.input}
            value={drawController.selectedLayer() ?? layers[0].id}
            onChange={(e) => drawController.moveSelectedToLayer(e.target.value)}
          >
            {layers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
                {l.visible ? '' : ' (hidden)'}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className={styles.actions}>
        <Button
          size="sm"
          icon="copy"
          onClick={() => setDuplicateFailed(!drawController.duplicate())}
        >
          Duplicate
        </Button>
        <Button size="sm" icon="trash" onClick={() => drawController.deleteSelected()}>
          Delete
        </Button>
      </div>
      {duplicateFailed && <p className={styles.hint}>This shape cannot be copied.</p>}
    </div>
  );
}
