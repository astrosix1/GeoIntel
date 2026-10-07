import type * as maplibregl from 'maplibre-gl';
import {
  TerraDraw,
  TerraDrawCircleMode,
  TerraDrawFreehandLineStringMode,
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
import { captureMapImage } from './snapshot';
import { cleanStyle, colorOf, dashOf, fillOf, HIGHLIGHT_OPACITY, highlightColorOf, highlightWidthOf, widthOf } from './style';
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
  | 'freehand'
  | 'highlighter';

export type DrawFeature = GeoJSONStoreFeatures;

export interface DrawHandlers {
  // Fires whenever a shape is added, moved, reshaped, restyled or removed (and while one is being drawn).
  onChange: (features: DrawFeature[]) => void;
  onSelect: (id: string | null) => void;
  onHistory: (state: { canUndo: boolean; canRedo: boolean }) => void;
  // The engine changed the tool itself (a new text label is selected straight away so its words can be typed).
  onTool: (tool: DrawTool) => void;
  // The layer a newly drawn shape goes on.
  getActiveLayer: () => string;
  // A shape has just been drawn (not edited): for announcing it.
  onDrawn: (feature: DrawFeature) => void;
}

export interface DrawEngine {
  // `null` hides the tool: the drawing stays on the map but nothing can be drawn or edited.
  setTool: (tool: DrawTool | null) => void;
  undo: () => void;
  redo: () => void;
  deleteSelected: () => void;
  clear: () => void;
  // The shapes on the map now (those on hidden layers are not).
  features: () => DrawFeature[];
  // Every shape, hidden or not, each with its layer id in `properties.layer`: what a saved drawing is made of.
  allFeatures: () => DrawFeature[];
  selected: () => DrawFeature | null;
  // Changes the style, name or note of the selected shape. A field set to undefined is cleared.
  setStyle: (change: Partial<Record<keyof ShapeStyle, unknown>>) => void;
  // Replaces everything with these shapes (each with its layer id in `properties.layer`), clearing the undo history. Shapes the
  // engine refuses are counted, not fatal.
  load: (features: DrawFeature[]) => { added: number; rejected: number };
  // Selects a shape by id (from the shape list) and switches to the Select tool.
  selectShape: (id: string) => void;
  // Which layer the selected shape is on, and moving it to another.
  selectedLayer: () => string | null;
  moveSelectedToLayer: (layerId: string) => void;
  // The layers whose shapes are not shown. Their shapes are taken off the map and put back when the layer is shown again.
  setHiddenLayers: (ids: Set<string>) => void;
  // How many shapes each layer holds, hidden ones included.
  counts: () => Record<string, number>;
  // Removes every shape on a layer (the layer itself is removed by the caller).
  deleteLayerShapes: (layerId: string) => void;
  // Copies the selected shape a little way over and selects the copy. False if the copy was refused.
  duplicateSelected: () => boolean;
  // The map as it looks now, drawing included, as a PNG (with the map credits and, if given, a title). Null if it could not be taken.
  captureImage: (title: string | null) => Promise<Blob | null>;
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
// The highlighter: a wide, see-through stroke in a marker colour.
const HIGHLIGHTER_STYLE = {
  lineStringColor: (f: DrawFeature) => highlightColorOf(f.properties) as HexColor,
  lineStringWidth: (f: DrawFeature) => highlightWidthOf(f.properties),
  lineStringOpacity: HIGHLIGHT_OPACITY,
};
const CORNER_STYLE = { closingPointColor: WHITE, closingPointOutlineColor: color, coordinatePointColor: color };

// Shapes the user sees: the helper points the engine adds while drawing are excluded.
const SHAPE_MODES = new Set(['point', 'text', 'linestring', 'arrow', 'angle', 'polygon', 'rectangle', 'circle', 'freehand', 'highlighter']);

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
      // Rectangle, circle and the freehand tools accept either press-and-drag or click, move and click again.
      new TerraDrawRectangleMode({ styles: POLYGON_STYLE, drawInteraction: 'click-move-or-drag' }),
      // The globe projection keeps the circle a true circle on the sphere at any latitude, on the flat map too.
      new TerraDrawCircleMode({ styles: POLYGON_STYLE, projection: 'globe', drawInteraction: 'click-move-or-drag' }),
      new TerraDrawFreehandMode({ styles: POLYGON_STYLE, drawInteraction: 'click-move-or-drag' }),
      // Press and drag to lay a marker stroke; it is a line, not an area, so it measures nothing.
      new TerraDrawFreehandLineStringMode({ modeName: 'highlighter', styles: HIGHLIGHTER_STYLE, drawInteraction: 'click-move-or-drag' }),
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
          highlighter: { feature: { draggable: true } },
        },
        styles: {
          // A selected highlighter stroke keeps its marker colour and thickness (only more solid), so the stroke being edited
          // can still be seen; every other line turns amber.
          selectedLineStringColor: (f: DrawFeature) => (f.properties?.mode === 'highlighter' ? (highlightColorOf(f.properties) as HexColor) : SELECTED),
          selectedLineStringWidth: (f: DrawFeature) => (f.properties?.mode === 'highlighter' ? highlightWidthOf(f.properties) : 4),
          selectedLineStringOpacity: (f: DrawFeature) => (f.properties?.mode === 'highlighter' ? 0.75 : 1),
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
  // Layer membership is kept here, beside the shapes, not in their properties: a layer change is not an undo step, and a
  // shape keeps its layer if it is hidden and shown again.
  const layerOf = new Map<string, string>();
  // Shapes on hidden layers, taken off the map until their layer is shown again.
  const stash = new Map<string, DrawFeature>();
  let hidden = new Set<string>();

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
  draw.on('finish', (id, context) => {
    const feature = draw.getSnapshotFeature(id);
    if (feature && isShape(feature) && !layerOf.has(String(id))) layerOf.set(String(id), handlers.getActiveLayer());
    if (feature && isShape(feature) && context.action === 'draw') handlers.onDrawn(feature);
    if (feature?.properties?.mode !== 'text') return;
    draw.setMode('select');
    draw.selectFeature(id);
    handlers.onTool('select');
  });

  draw.start();
  draw.setMode('render');

  const visibleShapes = () => draw.getSnapshot().filter(isShape);
  const layerForShape = (id: string | number | undefined) => layerOf.get(String(id)) ?? handlers.getActiveLayer();

  // What a shape is stored as while it is off the map and when it goes back: its mode and our own fields only, with its id.
  function plain(feature: DrawFeature): DrawFeature {
    const properties: Record<string, string | number | boolean> = {};
    for (const [key, value] of Object.entries(feature.properties ?? {})) {
      if (key === 'mode' || key === 'color' || key === 'width' || key === 'fill' || key === 'dash' || key === 'label' || key === 'note') {
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') properties[key] = value;
      }
    }
    const shape = { type: 'Feature', geometry: feature.geometry, properties } as DrawFeature;
    if (feature.id !== undefined) shape.id = feature.id;
    return shape;
  }

  // Takes the shapes of hidden layers off the map and puts back those whose layer is shown.
  function applyHidden() {
    // Each step is one call for all the shapes, not one per shape: the engine redraws after every call, so a layer of hundreds
    // of shapes would otherwise take seconds to hide or show.
    const toHide = visibleShapes().filter((f) => f.id !== undefined && hidden.has(layerForShape(f.id)));
    if (toHide.length > 0) {
      if (selected !== null && toHide.some((f) => String(f.id) === selected)) draw.deselectFeature(selected);
      for (const feature of toHide) stash.set(String(feature.id), plain(feature));
      draw.removeFeatures(toHide.map((f) => f.id as string | number));
    }
    const toShow = [...stash].filter(([id]) => !hidden.has(layerForShape(id)));
    if (toShow.length > 0) {
      const results = draw.addFeatures(toShow.map(([, feature]) => feature));
      results.forEach((result, i) => {
        if (result.valid) stash.delete(toShow[i][0]);
      });
    }
    publishFeatures();
  }

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
      stash.clear();
      layerOf.clear();
      draw.clear();
      publishFeatures();
      publishHistory();
    },
    features: visibleShapes,
    allFeatures: () => {
      const withLayer = (f: DrawFeature): DrawFeature => ({ ...f, properties: { ...f.properties, layer: layerForShape(f.id) } }) as DrawFeature;
      return [...visibleShapes(), ...stash.values()].map(withLayer);
    },
    selected: selectedFeature,
    selectedLayer: () => (selected === null ? null : layerForShape(selected)),
    moveSelectedToLayer(layerId) {
      if (selected === null) return;
      layerOf.set(selected, layerId);
      applyHidden(); // the shape may have moved to a hidden layer
      handlers.onChange(visibleShapes());
    },
    load(features) {
      stash.clear();
      layerOf.clear();
      draw.clear();
      // One call for the whole drawing (see applyHidden); the results line up with the shapes that were given.
      const results = draw.addFeatures(features.map(plain));
      let added = 0;
      let rejected = 0;
      results.forEach((result, i) => {
        if (!result.valid) {
          rejected += 1;
          return;
        }
        added += 1;
        const layer = features[i].properties?.layer;
        const id = result.id ?? features[i].id;
        if (id !== undefined && typeof layer === 'string') layerOf.set(String(id), layer);
      });
      draw.clearUndoRedoHistory();
      applyHidden();
      publishHistory();
      return { added, rejected };
    },
    selectShape(id) {
      if (selected !== null && selected !== id) draw.deselectFeature(selected);
      if (draw.getMode() !== 'select') draw.setMode('select');
      if (draw.hasFeature(id)) draw.selectFeature(id);
      handlers.onTool('select');
    },
    setHiddenLayers(ids) {
      hidden = new Set(ids);
      applyHidden();
    },
    counts() {
      const counts: Record<string, number> = {};
      for (const f of visibleShapes()) counts[layerForShape(f.id)] = (counts[layerForShape(f.id)] ?? 0) + 1;
      for (const id of stash.keys()) counts[layerForShape(id)] = (counts[layerForShape(id)] ?? 0) + 1;
      return counts;
    },
    deleteLayerShapes(layerId) {
      const ids = visibleShapes().filter((f) => layerForShape(f.id) === layerId && f.id !== undefined).map((f) => f.id as string | number);
      if (selected !== null && ids.map(String).includes(selected)) draw.deselectFeature(selected);
      if (ids.length > 0) draw.removeFeatures(ids);
      for (const id of [...stash.keys()]) if (layerForShape(id) === layerId) stash.delete(id);
      for (const [id, layer] of [...layerOf]) if (layer === layerId) layerOf.delete(id);
      publishFeatures();
    },
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
        layerOf.set(String(copy.id), layerForShape(selected));
        draw.deselectFeature(selected);
        draw.selectFeature(copy.id);
      }
      publishFeatures();
      return true;
    },
    captureImage: (title) => captureMapImage(map, title),
    destroy() {
      draw.stop();
    },
  };
}
