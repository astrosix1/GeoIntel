import type * as maplibregl from 'maplibre-gl';
import { arrowHeads } from './arrows';
import type { DrawFeature } from './engine';
import { labelsFor } from './measure';
import type { LabelOptions } from './measure';

// The map layers that sit on top of the drawing: arrowheads, and the text (measurements, names, Text-tool words).
const LABEL_SOURCE = 'draw-measure';
const LABEL_LAYER = 'draw-measure-labels';
const ARROW_SOURCE = 'draw-arrows';
const ARROW_LAYER = 'draw-arrow-heads';
const ARROW_IMAGE = 'draw-arrowhead';

// A white triangle pointing up with its tip at the top edge, registered as an SDF image so each arrow can be coloured.
function addArrowImage(map: maplibregl.Map): void {
  if (map.hasImage(ARROW_IMAGE)) return;
  const size = 32;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  if (!context) return;
  context.fillStyle = '#ffffff';
  context.beginPath();
  context.moveTo(16, 0);
  context.lineTo(29, 30);
  context.lineTo(16, 23);
  context.lineTo(3, 30);
  context.closePath();
  context.fill();
  map.addImage(ARROW_IMAGE, context.getImageData(0, 0, size, size), { sdf: true, pixelRatio: 2 });
}

export function ensureDrawLayers(map: maplibregl.Map): void {
  addArrowImage(map);
  if (!map.getSource(ARROW_SOURCE)) {
    map.addSource(ARROW_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer(ARROW_LAYER)) {
    map.addLayer({
      id: ARROW_LAYER,
      type: 'symbol',
      source: ARROW_SOURCE,
      layout: {
        'icon-image': ARROW_IMAGE,
        'icon-rotate': ['get', 'bearing'],
        'icon-rotation-alignment': 'map',
        'icon-pitch-alignment': 'map',
        'icon-anchor': 'top',
        'icon-size': 1.7,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
      paint: { 'icon-color': ['get', 'color'] },
    });
  } else {
    map.moveLayer(ARROW_LAYER);
  }
  if (!map.getSource(LABEL_SOURCE)) {
    map.addSource(LABEL_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  }
  if (!map.getLayer(LABEL_LAYER)) {
    map.addLayer({
      id: LABEL_LAYER,
      type: 'symbol',
      source: LABEL_SOURCE,
      layout: {
        'text-field': ['get', 'text'],
        'text-font': ['Noto Sans Bold'],
        // Words the user typed are the biggest; totals next; the per-segment and per-corner figures are smaller. Angles
        // sit off their corner and names above their shape.
        'text-size': ['match', ['get', 'kind'], 'text', 16, 'name', 14, 'total', 13, 11],
        'text-offset': ['match', ['get', 'kind'], 'angle', ['literal', [1.6, -1.1]], 'name', ['literal', [0, -1.7]], ['literal', [0, 0]]],
        'text-line-height': 1.2,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
        'text-padding': 2,
      },
      paint: {
        // The Text tool takes the shape's colour; everything else has a fixed, readable one. A white word gets a dark halo.
        'text-color': [
          'match', ['get', 'kind'],
          'text', ['coalesce', ['get', 'color'], '#0f172a'],
          'angle', '#9a3412',
          'segment', '#1e3a8a',
          '#0f172a',
        ],
        'text-halo-color': ['case', ['all', ['==', ['get', 'kind'], 'text'], ['==', ['get', 'color'], '#ffffff']], '#0f172a', '#ffffff'],
        'text-halo-width': 2,
      },
    });
  } else {
    // Keep the text above anything added since (the drawing's own layers are added when the engine starts).
    map.moveLayer(LABEL_LAYER);
  }
}

// Redraws the arrowheads and the text from the shapes' own geometry and properties.
export function showDrawLayers(map: maplibregl.Map, features: DrawFeature[], options: LabelOptions): void {
  const labels = map.getSource(LABEL_SOURCE) as maplibregl.GeoJSONSource | undefined;
  labels?.setData({
    type: 'FeatureCollection',
    features: labelsFor(features, options).map((label) => ({
      type: 'Feature',
      properties: { text: label.text, id: label.id, kind: label.kind, color: label.color ?? null },
      geometry: { type: 'Point', coordinates: label.position },
    })),
  });
  const arrows = map.getSource(ARROW_SOURCE) as maplibregl.GeoJSONSource | undefined;
  arrows?.setData({
    type: 'FeatureCollection',
    features: arrowHeads(features).map((head) => ({
      type: 'Feature',
      properties: { bearing: head.bearing, color: head.color, id: head.id },
      geometry: { type: 'Point', coordinates: head.position },
    })),
  });
}
