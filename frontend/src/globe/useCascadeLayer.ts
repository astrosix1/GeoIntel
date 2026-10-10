import { useEffect } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { useUiStore } from '../state/uiStore';
import { syncCascadeLayer } from './cascadeLayer';

// Keeps the exposure colours on the map in step with the latest cascade result (and puts them back after a base-style change).
export function useCascadeLayer(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean) {
  const result = useUiStore((s) => s.cascadeResult);
  const inEvents = useUiStore((s) => s.activeMode) === 'events';
  // The result is kept when the mode changes; it is only drawn while Events is showing.
  const drawn = inEvents ? result : null;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const apply = () => syncCascadeLayer(map, drawn);
    apply();
    map.on('style.load', apply);
    return () => {
      map.off('style.load', apply);
    };
  }, [mapRef, mapReady, drawn]);
}
