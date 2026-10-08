import { useEffect, useState } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useWeatherLayersQuery } from '../state/queries';
import { useNow } from '../state/useNow';
import { useUiStore } from '../state/uiStore';
import { nearestTime, syncWeatherLayers, todayUtc, yesterdayUtc } from './weatherLayers';

// Keeps the forecast field and the satellite overlays on the map in step with the Layers menu and the forecast bar. A forecast
// layer is asked for only while it is on; dragging the forecast bar is smoothed so each pause draws one set of tiles.
export function useWeatherLayers(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean) {
  const mode = useUiStore((s) => s.activeMode);
  const field = useUiStore((s) => s.weatherField);
  const forecastTime = useUiStore((s) => s.forecastTime);
  const clouds = useUiStore((s) => s.cloudsOn);
  const fires = useUiStore((s) => s.firesOn);
  const satellite = useUiStore((s) => s.satellite);
  const inWeather = mode === 'weather';
  const now = useNow(60_000).getTime();
  const { data } = useWeatherLayersQuery(inWeather && field !== null);

  const layer = field && data ? data.layers[field] : undefined;
  const wanted = layer ? nearestTime(layer.times, forecastTime ?? now) : null;

  // The time actually drawn trails the slider by a moment, and is only ever one the current layer can draw (each layer has its own
  // hours; asking for another makes the service answer with an error instead of a picture).
  const [lagging, setLagging] = useState<string | null>(wanted);
  useEffect(() => {
    const id = window.setTimeout(() => setLagging(wanted), 180);
    return () => window.clearTimeout(id);
  }, [wanted]);
  const time = lagging && layer?.times.includes(lagging) ? lagging : wanted;

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const apply = () =>
      syncWeatherLayers(
        map,
        inWeather
          ? { field, wmsLayer: layer?.wms_layer ?? null, time, clouds, cloudsDate: yesterdayUtc(now), fires, firesDate: todayUtc(now), darkBase: satellite }
          : null,
      );
    apply();
    // A new base style (satellite, topography) drops every added layer, so put them back.
    map.on('style.load', apply);
    return () => {
      map.off('style.load', apply);
    };
  }, [mapRef, mapReady, inWeather, field, layer?.wms_layer, time, clouds, fires, satellite, now]);
}
