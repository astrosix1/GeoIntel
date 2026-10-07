import { useRef, useState } from 'react';
import { DrawingError } from '../../api/client';
import PremiumGate from '../../components/PremiumGate';
import { useDrawStore } from '../../state/drawStore';
import { fetchDrawing, useDeleteDrawingMutation, useDrawingsQuery, useSaveDrawingMutation } from '../../state/drawQueries';
import { useEntitlements } from '../../state/queries';
import Button from '../../ui/Button';
import { MAX_BYTES, drawingSize, exportFileName, toGeoJSON } from './drawfile';
import type { ParseError } from './drawfile';
import { DEFAULT_NAME, saveDraft } from './draft';
import { currentDrawing, openDrawing, startNewDrawing } from './session';
import styles from './DrawingsPanel.module.css';

const SAVE_ERRORS: Record<string, string> = {
  limit_reached: 'You have reached the limit of saved drawings. Delete one to save another.',
  too_large: 'This drawing is too large to save. Remove some shapes or notes.',
  invalid: 'This drawing could not be saved because part of it was not accepted.',
  unavailable: 'Saving is not available right now. Your drawing is still kept in this browser.',
  sign_in_required: 'Sign in to save drawings.',
  premium_required: 'Saving drawings is a premium feature.',
};
const FILE_ERRORS: Record<ParseError, string> = {
  format: 'That file is not a drawing or GeoJSON file.',
  empty: 'That file has no shapes in it.',
  too_many_shapes: 'That file has too many shapes (the limit is 500).',
  too_many_vertices: 'That file has too many points (the limit is 20,000).',
  too_large: 'That file is too large.',
};
const MAX_IMPORT_BYTES = 2_000_000;

function errorText(error: unknown, table: Record<string, string>): string {
  const kind = error instanceof DrawingError ? error.kind : 'error';
  return table[kind] ?? 'Something went wrong. Please try again.';
}

// The drawing as a whole: its name and whether it is saved, saving it to the account (premium), opening or deleting saved
// drawings, starting a new one, and exporting or importing GeoJSON (premium). The drawing in progress is always kept as a
// draft in this browser, saved or not.
export default function DrawingsPanel() {
  const { premium } = useEntitlements();
  const drawing = useDrawStore((s) => s.drawing);
  const setDrawing = useDrawStore((s) => s.setDrawing);
  const dirty = useDrawStore((s) => s.dirty);
  const setDirty = useDrawStore((s) => s.setDirty);
  const shapeCount = useDrawStore((s) => s.shapeCount);
  const list = useDrawingsQuery(true);
  const save = useSaveDrawingMutation();
  const remove = useDeleteDrawingMutation();
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState(drawing.name);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  // A destructive step waits for a second press: replacing the drawing that has unsaved changes, or deleting a saved one.
  const [pending, setPending] = useState<{ type: 'new' | 'open' | 'import' | 'delete'; id?: string; file?: File } | null>(null);

  const hasWork = shapeCount > 0 && dirty;
  const status = drawing.id ? (dirty ? 'Unsaved changes' : 'Saved') : 'Not saved to your account';

  function commitName() {
    const clean = name.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 80) || DEFAULT_NAME;
    setName(clean);
    if (clean !== drawing.name) {
      setDrawing({ ...drawing, name: clean });
      setDirty(true);
      saveDraft({ drawing: { ...drawing, name: clean }, data: currentDrawing(), dirty: true });
    }
  }

  function doSave() {
    commitName();
    const finalName = name.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 80) || DEFAULT_NAME;
    const data = currentDrawing();
    if (drawingSize(data) > MAX_BYTES) {
      setMessage({ kind: 'error', text: SAVE_ERRORS.too_large });
      return;
    }
    save.mutate(
      { id: drawing.id, name: finalName, data },
      {
        onSuccess: (saved) => {
          setDrawing({ id: saved.id, name: saved.name });
          setDirty(false);
          saveDraft({ drawing: { id: saved.id, name: saved.name }, data, dirty: false });
          setMessage({ kind: 'ok', text: drawing.id ? 'Saved.' : 'Saved to your account.' });
        },
        onError: (error) => setMessage({ kind: 'error', text: errorText(error, SAVE_ERRORS) }),
      },
    );
  }

  function doNew() {
    startNewDrawing();
    setName(DEFAULT_NAME);
    setPending(null);
    setMessage(null);
  }

  async function doOpen(id: string) {
    setPending(null);
    try {
      const saved = await fetchDrawing(id);
      const result = openDrawing(saved.data, { id: saved.id, name: saved.name }, false);
      if (!result.ok) {
        setMessage({ kind: 'error', text: FILE_ERRORS[result.error] });
        return;
      }
      setName(saved.name);
      setMessage({ kind: 'ok', text: `Opened "${saved.name}".` });
    } catch (error) {
      setMessage({ kind: 'error', text: errorText(error, { ...SAVE_ERRORS, not_found: 'That drawing no longer exists.' }) });
    }
  }

  function doDelete(id: string) {
    setPending(null);
    remove.mutate(id, {
      onSuccess: () => {
        // The drawing on the map stays as it is; it is just no longer a saved one.
        if (drawing.id === id) {
          setDrawing({ id: null, name: drawing.name });
          setDirty(true);
        }
        setMessage({ kind: 'ok', text: 'Deleted.' });
      },
      onError: (error) => setMessage({ kind: 'error', text: errorText(error, SAVE_ERRORS) }),
    });
  }

  function doExport() {
    commitName();
    const text = toGeoJSON(currentDrawing(), name || DEFAULT_NAME);
    const url = URL.createObjectURL(new Blob([text], { type: 'application/geo+json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = exportFileName(name);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage({ kind: 'ok', text: 'Exported as GeoJSON.' });
  }

  async function doImport(file: File) {
    setPending(null);
    if (file.size > MAX_IMPORT_BYTES) {
      setMessage({ kind: 'error', text: FILE_ERRORS.too_large });
      return;
    }
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const title = (typeof (parsed as { name?: unknown })?.name === 'string' ? (parsed as { name: string }).name : file.name.replace(/\.[^.]+$/, '')).slice(0, 80) || DEFAULT_NAME;
      const result = openDrawing(parsed, { id: null, name: title }, true);
      if (!result.ok) {
        setMessage({ kind: 'error', text: FILE_ERRORS[result.error] });
        return;
      }
      setName(title);
      const { added, rejected, skipped } = result.result;
      const left = rejected + skipped;
      setMessage({ kind: 'ok', text: `Imported ${added} shape${added === 1 ? '' : 's'}${left ? `; ${left} shape${left === 1 ? '' : 's'} could not be drawn and ${left === 1 ? 'was' : 'were'} left out` : ''}.` });
    } catch {
      setMessage({ kind: 'error', text: FILE_ERRORS.format });
    }
  }

  // Replacing the drawing asks first when it has unsaved changes.
  function guarded(next: NonNullable<typeof pending>, run: () => void) {
    if (hasWork) setPending(next);
    else run();
  }

  const drawings = list.data?.drawings ?? [];

  return (
    <div className={styles.panel} role="group" aria-label="Drawings">
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Drawing name</span>
        <input
          className={styles.input}
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitName();
          }}
        />
      </label>
      <p className={styles.status}>
        {status}. The drawing in progress is also kept in this browser.
      </p>

      <div className={styles.actions}>
        <PremiumGate feature="Saved drawings" account>
          <Button size="sm" variant="primary" icon="save" disabled={save.isPending || shapeCount === 0} onClick={doSave}>
            {save.isPending ? 'Saving…' : drawing.id ? 'Save' : 'Save to account'}
          </Button>
        </PremiumGate>
        <Button size="sm" icon="plus" onClick={() => guarded({ type: 'new' }, doNew)}>
          New drawing
        </Button>
      </div>
      <div className={styles.actions}>
        <PremiumGate feature="Export" account>
          <Button size="sm" icon="download" disabled={shapeCount === 0} onClick={doExport}>
            Export GeoJSON
          </Button>
        </PremiumGate>
        <PremiumGate feature="Import" account>
          <Button size="sm" icon="upload" onClick={() => fileInput.current?.click()}>
            Import
          </Button>
        </PremiumGate>
        <input
          ref={fileInput}
          type="file"
          accept=".geojson,.json,application/geo+json,application/json"
          className={styles.hiddenInput}
          aria-label="Import a GeoJSON file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file) guarded({ type: 'import', file }, () => void doImport(file));
          }}
        />
      </div>

      {pending && pending.type !== 'delete' && (
        <div className={styles.confirm} role="alert">
          <span>This drawing has unsaved changes. Replace it?</span>
          <div className={styles.actions}>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                if (pending.type === 'new') doNew();
                else if (pending.type === 'open' && pending.id) void doOpen(pending.id);
                else if (pending.type === 'import' && pending.file) void doImport(pending.file);
              }}
            >
              Replace it
            </Button>
            <Button size="sm" onClick={() => setPending(null)}>
              Keep working
            </Button>
          </div>
        </div>
      )}

      {message && (
        <p className={message.kind === 'error' ? styles.error : styles.ok} role={message.kind === 'error' ? 'alert' : 'status'}>
          {message.text}
        </p>
      )}

      {premium && (
        <>
          <div className={styles.divider} />
          <span className={styles.fieldLabel}>Your saved drawings{list.data ? ` (${drawings.length} of ${list.data.limit})` : ''}</span>
          {list.isLoading && <p className={styles.hint}>Loading…</p>}
          {list.isError && <p className={styles.error}>Your drawings could not be loaded right now.</p>}
          {list.data && drawings.length === 0 && <p className={styles.hint}>Nothing saved yet. Draw something and press Save to account.</p>}
          <ul className={styles.list}>
            {drawings.map((d) => (
              <li key={d.id} className={`${styles.item} ${d.id === drawing.id ? styles.itemOpen : ''}`}>
                <div className={styles.itemMain}>
                  <span className={styles.itemName}>{d.name}</span>
                  <span className={styles.itemMeta}>
                    {d.shape_count} shape{d.shape_count === 1 ? '' : 's'} · {d.layer_count} layer{d.layer_count === 1 ? '' : 's'} · {new Date(d.updated_at).toLocaleDateString()}
                  </span>
                </div>
                <Button size="sm" onClick={() => guarded({ type: 'open', id: d.id }, () => void doOpen(d.id))}>
                  Open
                </Button>
                {pending?.type === 'delete' && pending.id === d.id ? (
                  <Button size="sm" variant="primary" onClick={() => doDelete(d.id)}>
                    Delete it
                  </Button>
                ) : (
                  <Button size="sm" icon="trash" aria-label={`Delete ${d.name}`} onClick={() => setPending({ type: 'delete', id: d.id })} />
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
