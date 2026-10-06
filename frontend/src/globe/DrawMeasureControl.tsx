import * as maplibregl from 'maplibre-gl';
import { MaplibreMeasureControl } from '@watergis/maplibre-gl-terradraw';
import '@watergis/maplibre-gl-terradraw/dist/maplibre-gl-terradraw.css';

// Item 10.6 — real draw/measure tool. `@watergis/maplibre-gl-terradraw` (the
// published npm name for the `maplibre-gl-terradraw` project referenced in
// the plan) wraps the `terra-draw` drawing engine with a MapLibre GL adapter
// and a Turf.js-powered measurement layer. `MaplibreMeasureControl` (a
// subclass of the plugin's base `MaplibreTerradrawControl`) is the plugin's
// OWN built-in measurement-display control: it already computes real
// Turf-based great-circle distance for lines and geodesic area for polygons
// and renders the result as an on-map label next to the drawn feature —
// confirmed from the package's shipped TypeScript declarations
// (MaplibreMeasureControl has measureLine/measurePolygon/measurePoint
// methods that label features on draw/edit). Using it directly means we
// don't need to hand-roll any custom measurement math or overlay UI, per
// the plan's "only build a custom display if the library doesn't already
// have one" guidance.
//
// `freehand` is one of the plugin's built-in TerraDraw mode names (see
// AvailableModes in the package's type declarations), so it's included
// below to satisfy the plan's third requirement (freehand drawing) with no
// extra code.
//
// This is a real `maplibregl.IControl`, so it mounts the same way as the
// existing `NavigationControl` in Globe.tsx (map.addControl(...)) — no new
// React mount point, no editing of the top bar, and it renders its own
// toggle button + expandable toolbar, so no extra button component is
// needed either.
export function createDrawMeasureControl(): MaplibreMeasureControl {
  return new MaplibreMeasureControl({
    modes: [
      // 'render' is the plugin's own special mode name for its
      // expand/collapse toggle button (confirmed from the plugin's compiled
      // source: addTerradrawButton special-cases mode === 'render' to render
      // a dedicated "expand or collapse drawing tool" button) — without it
      // in this list, the control mounts with no visible way to open the
      // toolbar at all, since `open: false` starts collapsed.
      'render',
      'point',
      'linestring',
      'polygon',
      'rectangle',
      'circle',
      'freehand',
      'select',
      'delete-selection',
      'delete',
    ],
    open: false,
    measureUnitType: 'metric',
    distanceUnit: 'kilometer',
    areaUnit: 'square kilometers',
  });
}

export type { MaplibreMeasureControl };
export type MapLibreMap = maplibregl.Map;
