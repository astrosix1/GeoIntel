import type * as maplibregl from 'maplibre-gl';
import {
  TerraDraw,
  TerraDrawCircleMode,
  TerraDrawFreehandMode,
  TerraDrawLineStringMode,
  TerraDrawPointMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
  TerraDrawRenderMode,
  TerraDrawSelectMode,
  TerraDrawSessionUndoRedo,
  TerraDrawUndoRedoKeyboardShortcuts,
} from 'terra-draw';
import type { GeoJSONStoreFeatures, HexColor } from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';
import { cleanStyle, colorOf, dashOf, fillOf, widthOf } from './style';
import type { ShapeStyle } from './style';

// The only file that talks to the drawing library (terra-draw). The rest of the app sees a small, plain interface, so the
// library can be upgraded or replaced without touching the interface or the store. Loaded on demand (a separate chunk)
// the first time the drawing tool is opened.

export type DrawTool =
  | 'select'
  | 'point'
  | 'text'
  | 'linestring'
  | 'arrow'
  | 'angle'
  | 'polygon'
  | 'rectangle'
  | 'circle'
  | 'freehand';

export type DrawFeature = GeoJSONStoreFeatures;

export interface DrawHandlers {
  // Fires whenever a shape is added, moved, reshaped, restyled or removed (and while one is being drawn).
  onChange: (features: DrawFeature[]) => void;
  onSelect: (id: string | null) => void;
  onHistory: (state: { canUndo: boolean; canRedo: boolean }) => void;
  // The engine changed the tool itself (a new text label is selected straight away so its words can be typed).
  onTool: (tool: DrawTool) => void;
}

export interface DrawEngine {
  // `null` hides the tool: the drawing stays on the map but nothing can be drawn or edited.
  setTool: (tool: DrawTool | null) => void;
  undo: () => void;
  redo: () => void;
  deleteSelected: () => void;
  clear: () => void;
  features: () => DrawFeature[];
  selected: () => DrawFeature | null;
  // Changes the style, name or note of the selected shape. A field set to undefined is cleared.
  setStyle: (change: Partial<Record<keyof ShapeStyle, unknown>>) => void;
  // Copies the selected shape a little way over and selects the copy. False if the copy was refused.
  duplicateSelected: () => boolean;
  destroy: () => void;
}

// Colours the engine needs as plain hex values (it cannot read CSS variables). The default blue reads on the dark map,
// the satellite imagery and the light map alike; each shape can pick another from the palette (style.ts).
const SELECTED: HexColor = '#f59e0b';
const WHITE: HexColor = '#ffffff';

// Per-shape styling: the engine asks for each shape's colour, width and so on, and we answer from the shape's own
// properties, so a restyled shape updates on its own and a saved drawing comes back looking the same.
const color = (f: DrawFeature) => colorOf(f.properties) as HexColor;
const width = (f: DrawFeature) => widthOf(f.properties);
const fill = (f: DrawFeature) => fillOf(f.properties);
const dash = (f: DrawFeature) => dashOf(f.properties);
// The Text tool is just its words: its anchor point is invisible, except while it is selected.
const hideForText = (f: DrawFeature) => (f.properties?.mode === 'text' ? 0 : 1);

// The small points the engine adds to a shape while it is drawn or selected (its corners, the closing point, snapping and
// mid points). They carry the shape's mode name too, so they are told apart by these flags.
const HELPER_FLAGS = ['coordinatePoint', 'closingPoint', 'snappingPoint', 'midPoint', 'selectionPoint'];

const POINT_STYLE = {
  pointColor: color,
  pointWidth: 6,
  pointOpacity: hideForText,
  pointOutlineColor: WHITE,
  pointOutlineWidth: 2,
  pointOutlineOpacity: hideForText,
};
const LINE_STYLE = { lineStringColor: color, lineStringWidth: width, lineStringDash: dash };
const POLYGON_STYLE = { fillColor: color, fillOpacity: fill, outlineColor: color, outlineWidth: width };
const CORNER_STYLE = { closingPointColor: WHITE, closingPointOutlineColor: color, coordinatePointColor: color };

// Shapes the user sees: the helper points the engine adds while drawing are excluded.
const SHAPE_MODES = new Set(['point', 'text', 'linestring', 'arrow', 'angle', 'polygon', 'rectangle', 'circle', 'freehand']);

function isShape(feature: DrawFeature): boolean {
  const mode = feature.properties?.mode;
  if (typeof mode !== 'string' || !SHAPE_MODES.has(mode)) return false;
  return !HELPER_FLAGS.some((flag) => feature.properties?.[flag]);
}

type Coordinates = number[] | Coordinates[];

// The engine refuses coordinates with more than nine decimal places, so a moved copy is rounded to that.
const round = (value: number) => Math.round(value * 1e9) / 1e9;

function shift(coordinates: Coordinates, dLon: number, dLat: number): Coordinates {
  if (typeof coordinates[0] === 'number') {
    const [lon, lat] = coordinates as number[];
    return [round(lon + dLon), round(Math.max(-85, Math.min(85, lat + dLat)))];
  }
  return (coordinates as Coordinates[]).map((part) => shift(part, dLon, dLat));
}

export function createDrawEngine(map: maplibregl.Map, handlers: DrawHandlers): DrawEngine {
  const draw = new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({ map }),
    modes: [
      new TerraDrawPointMode({ styles: POINT_STYLE }),
      // The Text tool: a point whose words are the label (see measure.ts); the anchor is invisible.
      new TerraDrawPointMode({ modeName: 'text', styles: POINT_STYLE }),
      new TerraDrawLineStringMode({ styles: { ...LINE_STYLE, ...CORNER_STYLE }, snapping: { toCoordinate: true } }),
      // An arrow is a line that finishes on its second corner; the head is drawn by useDraw.
      new TerraDrawLineStringMode({
        modeName: 'arrow',
        styles: { ...LINE_STYLE, ...CORNER_STYLE },
        snapping: { toCoordinate: true },
        finishOnNthCoordinate: 2,
      }),
      // The angle tool is a line that finishes on its third corner: the end of one leg, the corner, the end of the other leg.
      new TerraDrawLineStringMode({
        modeName: 'angle',
        styles: { ...LINE_STYLE, ...CORNER_STYLE },
        snapping: { toCoordinate: true },
        finishOnNthCoordinate: 3,
      }),
      new TerraDrawPolygonMode({ styles: { ...POLYGON_STYLE, ...CORNER_STYLE }, snapping: { toCoordinate: true } }),
      new TerraDrawRectangleMode({ styles: POLYGON_STYLE }),
      // The globe projection keeps the circle a true circle on the sphere at any latitude, on the flat map too.
      new TerraDrawCircleMode({ styles: POLYGON_STYLE, projection: 'globe' }),
      new TerraDrawFreehandMode({ styles: POLYGON_STYLE }),
      new TerraDrawSelectMode({
        flags: {
          point: { feature: { draggable: true } },
          text: { feature: { draggable: true } },
          linestring: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
          // An arrow and an angle keep their corners: they can be moved but not added to or removed.
          arrow: { feature: { draggable: true, coordinates: { draggable: true } } },
          angle: { feature: { draggable: true, coordinates: { draggable: true } } },
          polygon: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
          rectangle: { feature: { draggable: true, coordinates: { resizable: 'opposite' } } },
          circle: { feature: { draggable: true, coordinates: { resizable: 'center-fixed' } } },
          freehand: { feature: { draggable: true } },
        },
        styles: {
          selectedLineStringColor: SELECTED,
          selectedPolygonColor: SELECTED,
          selectedPolygonOutlineColor: SELECTED,
          selectedPointColor: SELECTED,
          selectionPointColor: WHITE,
          selectionPointOutlineColor: SELECTED,
          midPointColor: SELECTED,
        },
      }),
      // Hidden: shapes keep the look of the mode they were drawn in, so this mode needs no styling of its own.
      new TerraDrawRenderMode({ modeName: 'render', styles: {} }),
    ],
    undoRedo: {
      sessionLevel: new TerraDrawSessionUndoRedo(),
      keyboardShortcuts: new TerraDrawUndoRedoKeyboardShortcuts(),
    },
  });

  let selected: string | null = null;

  const publishHistory = () => handlers.onHistory({ canUndo: draw.canUndo(), canRedo: draw.canRedo() });
  const publishFeatures = () => handlers.onChange(draw.getSnapshot().filter(isShape));

  draw.on('change', () => {
    publishFeatures();
    publishHistory();
  });
  draw.on('history', publishHistory);
  draw.on('select', (id) => {
    selected = String(id);
    handlers.onSelect(selected);
  });
  draw.on('deselect', () => {
    selected = null;
    handlers.onSelect(null);
  });
  // A new text label is selected straight away so its words can be typed in the panel.
  draw.on('finish', (id) => {
    const feature = draw.getSnapshotFeature(id);
    if (feature?.properties?.mode !== 'text') return;
    draw.setMode('select');
    draw.selectFeature(id);
    handlers.onTool('select');
  });

  draw.start();
  draw.setMode('render');

  const selectedFeature = (): DrawFeature | null => (selected === null ? null : (draw.getSnapshotFeature(selected) ?? null));

  return {
    setTool(tool) {
      const mode = tool ?? 'render';
      // Asking for the tool it is already in must do nothing: switching modes clears the selection.
      if (draw.getMode() === mode) return;
      draw.setMode(mode);
    },
    undo() {
      draw.undo();
      publishFeatures();
      publishHistory();
    },
    redo() {
      draw.redo();
      publishFeatures();
      publishHistory();
    },
    deleteSelected() {
      if (selected === null) return;
      const id = selected;
      draw.deselectFeature(id);
      draw.removeFeatures([id]);
    },
    clear() {
      draw.clear();
      publishFeatures();
      publishHistory();
    },
    features: () => draw.getSnapshot().filter(isShape),
    selected: selectedFeature,
    setStyle(change) {
      if (selected === null) return;
      const clean = cleanStyle(change as Record<string, unknown>);
      const update: Record<string, string | number | undefined> = {};
      for (const key of Object.keys(change) as (keyof ShapeStyle)[]) update[key] = clean[key];
      draw.updateFeatureProperties(selected, update);
      publishFeatures();
    },
    duplicateSelected() {
      const feature = selectedFeature();
      if (!feature) return false;
      // About 30 pixels over and down, whatever the zoom.
      const degrees = (30 * 360) / (512 * 2 ** map.getZoom());
      const geometry = { ...feature.geometry, coordinates: shift(feature.geometry.coordinates as Coordinates, degrees, -degrees * 0.6) };
      const properties: Record<string, string | number | boolean> = {};
      for (const [key, value] of Object.entries(feature.properties ?? {})) {
        if (key === 'selected' || key === 'currentlyDrawing' || key === 'edited' || HELPER_FLAGS.includes(key)) continue;
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') properties[key] = value;
      }
      const results = draw.addFeatures([{ type: 'Feature', geometry, properties } as DrawFeature]);
      if (results.some((r) => !r.valid)) return false;
      const copy = draw.getSnapshot().filter(isShape).at(-1);
      if (copy?.id !== undefined && selected !== null) {
        draw.deselectFeature(selected);
        draw.selectFeature(copy.id);
      }
      publishFeatures();
      return true;
    },
    destroy() {
      draw.stop();
    },
  };
}
