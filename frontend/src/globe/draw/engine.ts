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

// The only file that talks to the drawing library (terra-draw). The rest of the app sees a small, plain interface, so the
// library can be upgraded or replaced without touching the interface or the store. Loaded on demand (a separate chunk)
// the first time the drawing tool is opened.

export type DrawTool = 'select' | 'point' | 'linestring' | 'polygon' | 'rectangle' | 'circle' | 'freehand';

export type DrawFeature = GeoJSONStoreFeatures;

export interface DrawHandlers {
  // Fires whenever a shape is added, moved, reshaped or removed (and while one is being drawn).
  onChange: (features: DrawFeature[]) => void;
  onSelect: (id: string | null) => void;
  onHistory: (state: { canUndo: boolean; canRedo: boolean }) => void;
}

export interface DrawEngine {
  // `null` hides the tool: the drawing stays on the map but nothing can be drawn or edited.
  setTool: (tool: DrawTool | null) => void;
  undo: () => void;
  redo: () => void;
  deleteSelected: () => void;
  clear: () => void;
  features: () => DrawFeature[];
  destroy: () => void;
}

// Colours the engine needs as plain hex values (it cannot read CSS variables). A blue that reads on the dark map,
// the satellite imagery and the light map alike.
const STROKE: HexColor = '#3b82f6';
const FILL: HexColor = '#3b82f6';
const SELECTED: HexColor = '#f59e0b';
const WHITE: HexColor = '#ffffff';

// Shapes the user sees: the helper points the engine adds while drawing are excluded.
const SHAPE_MODES = new Set(['point', 'linestring', 'polygon', 'rectangle', 'circle', 'freehand']);

function isShape(feature: DrawFeature): boolean {
  const mode = feature.properties?.mode;
  return typeof mode === 'string' && SHAPE_MODES.has(mode);
}

export function createDrawEngine(map: maplibregl.Map, handlers: DrawHandlers): DrawEngine {
  const lineStyle = { lineStringColor: STROKE, lineStringWidth: 3 };
  const polygonStyle = { fillColor: FILL, fillOpacity: 0.2, outlineColor: STROKE, outlineWidth: 3 };

  const draw = new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({ map }),
    modes: [
      new TerraDrawPointMode({ styles: { pointColor: STROKE, pointWidth: 6, pointOutlineColor: WHITE, pointOutlineWidth: 2 } }),
      new TerraDrawLineStringMode({
        styles: { ...lineStyle, closingPointColor: WHITE, closingPointOutlineColor: STROKE, coordinatePointColor: STROKE },
        snapping: { toCoordinate: true },
        showCoordinatePoints: true,
      }),
      new TerraDrawPolygonMode({
        styles: { ...polygonStyle, closingPointColor: WHITE, closingPointOutlineColor: STROKE, coordinatePointColor: STROKE },
        snapping: { toCoordinate: true },
        showCoordinatePoints: true,
      }),
      new TerraDrawRectangleMode({ styles: polygonStyle }),
      // The globe projection keeps the circle a true circle on the sphere at any latitude, on the flat map too.
      new TerraDrawCircleMode({ styles: polygonStyle, projection: 'globe' }),
      new TerraDrawFreehandMode({ styles: { fillColor: FILL, fillOpacity: 0.2, outlineColor: STROKE, outlineWidth: 3 } }),
      new TerraDrawSelectMode({
        flags: {
          point: { feature: { draggable: true } },
          linestring: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
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
      // What the drawing looks like when the tool is hidden.
      new TerraDrawRenderMode({
        modeName: 'render',
        styles: { ...polygonStyle, ...lineStyle, pointColor: STROKE, pointWidth: 6, pointOutlineColor: WHITE, pointOutlineWidth: 2 },
      }),
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

  draw.start();
  draw.setMode('render');

  return {
    setTool(tool) {
      draw.setMode(tool ?? 'render');
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
    destroy() {
      draw.stop();
    },
  };
}
