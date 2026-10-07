import { useEffect, useMemo } from 'react';
import type { MutableRefObject } from 'react';
import type * as maplibregl from 'maplibre-gl';
import { isLiteDevice } from '../lite';
import { useRadarFramesQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import { syncRadar } from './radarLayer';

const FRAME_MS = 600;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// True when the loop should animate. Phones and low-core devices, and anyone
// who asked for reduced motion, get a still image of the latest frame (one
// raster layer instead of a dozen preloaded ones).
export function radarCanAnimate(): boolean {
  return !isLiteDevice() && !prefersReducedMotion();
}

// Radar for Weather mode: fetches the frame list, keeps the map layers in
// sync, runs the playback loop, and publishes the visible frame's time so
// the legend can show it.
export function useRadar(mapRef: MutableRefObject<maplibregl.Map | null>, mapReady: boolean) {
  const activeMode = useUiStore((s) => s.activeMode);
  const radarOn = useUiStore((s) => s.radarOn);
  const playing = useUiStore((s) => s.radarPlaying);
  const setRadarTime = useUiStore((s) => s.setRadarTime);
  const cursor = useUiStore((s) => s.radarCursor);
  const setCursor = useUiStore((s) => s.setRadarCursor);
  const setFrameTimes = useUiStore((s) => s.setRadarFrameTimes);

  const enabled = activeMode === 'weather' && radarOn;
  const { data } = useRadarFramesQuery(enabled);
  const animate = radarCanAnimate();

  // Every preloaded frame costs tile requests against RainViewer's per-IP
  // rate limit, so the loop uses every second frame (about 20 minutes apart,
  // newest included) rather than all of them.
  const frames = useMemo(() => {
    if (!data) return [];
    if (!animate) return data.frames.slice(-1);
    const last = data.frames.length - 1;
    return data.frames.filter((_, i) => (last - i) % 2 === 0);
  }, [data, animate]);

  // The cursor starts past the end so the first frame shown is the newest; it is clamped here.
  const shown = Math.min(cursor, Math.max(frames.length - 1, 0));

  useEffect(() => {
    if (!enabled || !animate || !playing || frames.length < 2) return;
    const id = window.setInterval(() => {
      const c = useUiStore.getState().radarCursor;
      setCursor((Math.min(c, frames.length - 1) + 1) % frames.length);
    }, FRAME_MS);
    return () => window.clearInterval(id);
  }, [enabled, animate, playing, frames.length, setCursor]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncRadar(map, enabled && data && frames.length ? { host: data.host, frames, index: shown } : null);
  }, [mapRef, mapReady, enabled, data, frames, shown]);

  // The timeline needs the times of the frames in use.
  const frameTimes = useMemo(() => (enabled ? frames.map((f) => f.time) : []), [enabled, frames]);
  useEffect(() => {
    setFrameTimes(frameTimes);
  }, [frameTimes, setFrameTimes]);

  const currentTime = enabled && frames[shown] ? frames[shown].time : null;
  useEffect(() => {
    setRadarTime(currentTime);
  }, [currentTime, setRadarTime]);
}
