import type * as maplibregl from 'maplibre-gl';
import type { CascadeResult } from '../api/types';

// The cascade result drawn on the map: each affected country filled by exposure, the trigger country in the accent colour. It reuses the
// country shapes the globe already loads for click-to-select (the source id is the one Globe.tsx adds), so no second download.
const COUNTRY_SOURCE = 'country-hit-test';
const LAYER = 'cascade-exposure-fill';
const BEFORE = ['crises-clusters', 'crises-halo', 'crises-points'];   // draw under the event pins

export const EXPOSURE_COLORS = { High: '#ff2d55', Moderate: '#ff9500', Low: '#ffd60a', Trigger: '#5aa0ff' } as const;

// Natural Earth gives some countries ISO_A2 "-99" (France, Norway); ISO_A2_EH is the fallback the click handler also uses.
const KEY: maplibregl.ExpressionSpecification = ['case', ['!=', ['get', 'ISO_A2'], '-99'], ['get', 'ISO_A2'], ['get', 'ISO_A2_EH']];

export function exposureColorExpression(result: CascadeResult): maplibregl.ExpressionSpecification {
  const by = (level: 'High' | 'Moderate' | 'Low') => result.effects.filter((e) => e.exposure === level).map((e) => e.iso);
  const expression: unknown[] = ['match', KEY];
  const trigger = result.trigger.country ? [result.trigger.country] : [];
  for (const [isos, color] of [[trigger, EXPOSURE_COLORS.Trigger], [by('High'), EXPOSURE_COLORS.High], [by('Moderate'), EXPOSURE_COLORS.Moderate], [by('Low'), EXPOSURE_COLORS.Low]] as const) {
    if (isos.length > 0) expression.push(isos, color);
  }
  expression.push('rgba(0,0,0,0)');
  return expression as maplibregl.ExpressionSpecification;
}

// Puts the result on the map, or takes it off when `result` is null. Safe to call again after a style change.
export function syncCascadeLayer(map: maplibregl.Map, result: CascadeResult | null): void {
  if (!result) {
    if (map.getLayer(LAYER)) map.removeLayer(LAYER);
    return;
  }
  if (!map.getSource(COUNTRY_SOURCE)) return;      // the country shapes are not in the style yet; the style.load handler tries again
  const color = exposureColorExpression(result);
  if (map.getLayer(LAYER)) {
    map.setPaintProperty(LAYER, 'fill-color', color);
    return;
  }
  const before = BEFORE.find((id) => map.getLayer(id));
  map.addLayer({ id: LAYER, type: 'fill', source: COUNTRY_SOURCE, paint: { 'fill-color': color, 'fill-opacity': 0.55 } }, before);
}
