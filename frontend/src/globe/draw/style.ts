// How a drawn shape looks, kept in the shape's own properties so it is saved with the drawing, copied by Duplicate, and
// read by the engine's per-shape styling. This file imports nothing so it can be unit-tested
// (frontend/tests/drawstyle.test.ts).

export type Dash = 'solid' | 'dashed';

// What a shape remembers about its looks and its words. Every field is optional: a shape with none looks like the default.
export interface ShapeStyle {
  color?: string; // one of the palette's values
  width?: number; // line and outline width in pixels, one of WIDTHS
  fill?: number; // fill opacity of an area, one of FILLS
  dash?: Dash; // line and outline pattern
  label?: string; // a name shown on the map
  note?: string; // longer text, shown in the panel
}

// A short palette that reads on the dark map, the light map and the satellite imagery. The amber used for the selected
// shape is deliberately not in it.
export const PALETTE: { value: string; label: string }[] = [
  { value: '#3b82f6', label: 'Blue' },
  { value: '#ef4444', label: 'Red' },
  { value: '#22c55e', label: 'Green' },
  { value: '#a855f7', label: 'Purple' },
  { value: '#0f172a', label: 'Black' },
  { value: '#ffffff', label: 'White' },
];

export const DEFAULT_COLOR = PALETTE[0].value;
export const WIDTHS: { value: number; label: string }[] = [
  { value: 2, label: 'Thin' },
  { value: 3, label: 'Medium' },
  { value: 5, label: 'Thick' },
];
export const DEFAULT_WIDTH = 3;
export const FILLS: { value: number; label: string }[] = [
  { value: 0, label: 'None' },
  { value: 0.2, label: 'Light' },
  { value: 0.4, label: 'Medium' },
];
export const DEFAULT_FILL = 0.2;

// The highlighter: a wide, see-through marker stroke, in colours that read as a marker pen on a map, in three thicknesses.
export const HIGHLIGHT_COLORS: { value: string; label: string }[] = [
  { value: '#facc15', label: 'Yellow' },
  { value: '#f472b6', label: 'Pink' },
  { value: '#4ade80', label: 'Green' },
  { value: '#38bdf8', label: 'Blue' },
  { value: '#fb923c', label: 'Orange' },
];
export const HIGHLIGHT_WIDTHS: { value: number; label: string }[] = [
  { value: 12, label: 'Thin' },
  { value: 20, label: 'Medium' },
  { value: 32, label: 'Thick' },
];
export const DEFAULT_HIGHLIGHT_COLOR = HIGHLIGHT_COLORS[0].value;
export const DEFAULT_HIGHLIGHT_WIDTH = 20;
export const HIGHLIGHT_OPACITY = 0.4;

export const MAX_LABEL_LENGTH = 80;
export const MAX_NOTE_LENGTH = 2000;

type Props = Record<string, unknown> | null | undefined;

const isHex = (value: unknown): value is string => typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value);

export function colorOf(props: Props): string {
  const value = props?.color;
  return isHex(value) && PALETTE.some((c) => c.value === value.toLowerCase()) ? value.toLowerCase() : DEFAULT_COLOR;
}

export function highlightColorOf(props: Props): string {
  const value = props?.color;
  return isHex(value) && HIGHLIGHT_COLORS.some((c) => c.value === value.toLowerCase()) ? value.toLowerCase() : DEFAULT_HIGHLIGHT_COLOR;
}

export function highlightWidthOf(props: Props): number {
  const value = props?.width;
  return typeof value === 'number' && HIGHLIGHT_WIDTHS.some((w) => w.value === value) ? value : DEFAULT_HIGHLIGHT_WIDTH;
}

export function widthOf(props: Props): number {
  const value = props?.width;
  return typeof value === 'number' && WIDTHS.some((w) => w.value === value) ? value : DEFAULT_WIDTH;
}

export function fillOf(props: Props): number {
  const value = props?.fill;
  return typeof value === 'number' && FILLS.some((f) => f.value === value) ? value : DEFAULT_FILL;
}

// The line pattern as the engine wants it: a [dash, gap] pair for a dashed line, none for a solid one.
export function dashOf(props: Props): [number, number] | undefined {
  return props?.dash === 'dashed' ? [8, 6] : undefined;
}

// A name or note cleaned for storing: a string, trimmed of control characters and cut to its limit. Anything else is
// dropped. (Text is only ever shown as text, never as HTML.)
export function cleanText(value: unknown, max: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  // eslint-disable-next-line no-control-regex
  const text = value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').slice(0, max);
  return text.trim() === '' ? undefined : text;
}

// Only the style fields we know, each checked, so nothing unexpected is stored on a shape.
export function cleanStyle(input: Record<string, unknown>): ShapeStyle {
  const style: ShapeStyle = {};
  // A shape's colour and width are one of the ordinary choices or one of the highlighter's.
  if (typeof input.color === 'string' && [...PALETTE, ...HIGHLIGHT_COLORS].some((c) => c.value === input.color)) style.color = input.color;
  if (typeof input.width === 'number' && [...WIDTHS, ...HIGHLIGHT_WIDTHS].some((w) => w.value === input.width)) style.width = input.width;
  if (typeof input.fill === 'number' && FILLS.some((f) => f.value === input.fill)) style.fill = input.fill;
  if (input.dash === 'solid' || input.dash === 'dashed') style.dash = input.dash;
  const label = cleanText(input.label, MAX_LABEL_LENGTH);
  if (label !== undefined) style.label = label;
  const note = cleanText(input.note, MAX_NOTE_LENGTH);
  if (note !== undefined) style.note = note;
  return style;
}
