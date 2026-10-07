import { useState } from 'react';
import { useDrawStore } from '../../state/drawStore';
import Button, { IconButton } from '../../ui/Button';
import { drawController } from './controller';
import { MAX_LAYER_NAME, MAX_LAYER_NOTE, MAX_LAYERS } from './drawlayers';
import type { DrawLayer } from './drawlayers';
import styles from './LayersPanel.module.css';

// The active layer's name and note keep their own text while it is typed and hand it to the drawing when the field is left.
function LayerDetails({ layer }: { layer: DrawLayer }) {
  const rename = useDrawStore((s) => s.renameLayer);
  const setNote = useDrawStore((s) => s.setLayerNote);
  const [name, setName] = useState(layer.name);
  const [note, setNoteText] = useState(layer.note);
  return (
    <>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Layer name</span>
        <input
          className={styles.input}
          value={name}
          maxLength={MAX_LAYER_NAME}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => rename(layer.id, name)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') rename(layer.id, name);
          }}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Layer note</span>
        <textarea
          className={styles.textarea}
          value={note}
          maxLength={MAX_LAYER_NOTE}
          rows={3}
          placeholder="Optional: what this scenario assumes"
          onChange={(e) => setNoteText(e.target.value)}
          onBlur={() => setNote(layer.id, note)}
        />
      </label>
    </>
  );
}

// The drawing's layers, for planning scenarios: each layer is shown or hidden on its own, so outcomes can be compared by
// switching them on and off. New shapes go on the active layer.
export default function LayersPanel() {
  const layers = useDrawStore((s) => s.layers);
  const activeLayerId = useDrawStore((s) => s.activeLayerId);
  const addLayer = useDrawStore((s) => s.addLayer);
  const toggleLayer = useDrawStore((s) => s.toggleLayer);
  const soloLayer = useDrawStore((s) => s.soloLayer);
  const setActiveLayer = useDrawStore((s) => s.setActiveLayer);
  const removeLayer = useDrawStore((s) => s.removeLayer);
  useDrawStore((s) => s.revision); // the counts change as shapes are drawn and removed
  const [confirming, setConfirming] = useState(false);

  const counts = drawController.counts();
  const active = layers.find((l) => l.id === activeLayerId) ?? layers[0];
  const onlyActiveShown = layers.every((l) => l.visible === (l.id === active.id));

  return (
    <div className={styles.panel} role="group" aria-label="Layers">
      <ul className={styles.list}>
        {layers.map((layer) => (
          <li key={layer.id} className={`${styles.row} ${layer.id === active.id ? styles.rowActive : ''}`}>
            <IconButton
              icon={layer.visible ? 'eye' : 'eye-off'}
              size="sm"
              label={`${layer.visible ? 'Hide' : 'Show'} ${layer.name}`}
              aria-pressed={layer.visible}
              onClick={() => toggleLayer(layer.id)}
            />
            <button
              type="button"
              className={styles.name}
              aria-current={layer.id === active.id ? 'true' : undefined}
              title="Draw on this layer"
              onClick={() => {
                setActiveLayer(layer.id);
                setConfirming(false);
              }}
            >
              <span className={layer.visible ? '' : styles.dim}>{layer.name}</span>
            </button>
            <span className={styles.count} aria-label={`${counts[layer.id] ?? 0} shapes`}>
              {counts[layer.id] ?? 0}
            </span>
          </li>
        ))}
      </ul>
      <Button size="sm" icon="plus" disabled={layers.length >= MAX_LAYERS} onClick={() => addLayer()}>
        New layer
      </Button>
      <p className={styles.hint}>New shapes go on the highlighted layer. Use the eye to show or hide a layer.</p>

      <div className={styles.divider} />
      <LayerDetails key={active.id} layer={active} />
      <div className={styles.actions}>
        <Button size="sm" disabled={layers.length < 2} onClick={() => soloLayer(active.id)}>
          {onlyActiveShown && layers.length > 1 ? 'Show all layers' : 'Show only this layer'}
        </Button>
        {!confirming ? (
          <Button size="sm" icon="trash" disabled={layers.length < 2} onClick={() => setConfirming(true)}>
            Delete layer
          </Button>
        ) : (
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              drawController.deleteLayerShapes(active.id);
              removeLayer(active.id);
              setConfirming(false);
            }}
          >
            Delete it and its {counts[active.id] ?? 0} shapes
          </Button>
        )}
      </div>
    </div>
  );
}
