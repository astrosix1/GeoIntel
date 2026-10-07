import { drawingSize, MAX_BYTES, parseDrawing } from './drawfile.ts';
import type { DrawingData } from './drawfile.ts';

// The drawing in progress, kept in this browser so a refresh or a closed tab does not lose it (for everyone, saved to an
// account or not). It is only a draft: saving to the account is what makes a drawing last (and is premium). Storage can be
// blocked or full, in which case there is simply no draft. This file imports only pure modules so it can be unit-tested
// (frontend/tests/drawdraft.test.ts).

export interface Draft {
  // The saved drawing this draft came from, if any, and the name it is working under.
  drawing: { id: string | null; name: string };
  data: DrawingData;
  // Changed since it was last saved or opened (a draft is assumed to be unless it says otherwise).
  dirty?: boolean;
}

export const DRAFT_KEY = 'geointel.drawDraft';
export const DEFAULT_NAME = 'Untitled drawing';

export function serializeDraft(draft: Draft): string | null {
  if (drawingSize(draft.data) > MAX_BYTES) return null;
  return JSON.stringify({ id: draft.drawing.id, name: draft.drawing.name, data: draft.data, dirty: draft.dirty !== false });
}

export function parseDraft(text: string | null): Draft | null {
  if (!text) return null;
  try {
    const raw = JSON.parse(text) as { id?: unknown; name?: unknown; data?: unknown; dirty?: unknown };
    const read = parseDrawing(raw.data);
    if (!read.ok) return null;
    return {
      drawing: {
        id: typeof raw.id === 'string' && /^[0-9a-f-]{36}$/i.test(raw.id) ? raw.id : null,
        name: typeof raw.name === 'string' && raw.name.trim() ? raw.name.slice(0, 80) : DEFAULT_NAME,
      },
      data: read.drawing.data,
      dirty: raw.dirty !== false,
    };
  } catch {
    return null;
  }
}

export function loadDraft(): Draft | null {
  try {
    return parseDraft(localStorage.getItem(DRAFT_KEY));
  } catch {
    return null;
  }
}

// An empty drawing is not worth keeping: the draft is removed instead.
export function saveDraft(draft: Draft): void {
  try {
    if (draft.data.features.length === 0) {
      localStorage.removeItem(DRAFT_KEY);
      return;
    }
    const text = serializeDraft(draft);
    if (text) localStorage.setItem(DRAFT_KEY, text);
  } catch {
    /* storage unavailable or full: no draft */
  }
}

export function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* nothing to clear */
  }
}
