import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchActiveStorms } from '../api/client';
import type { CrisisSummary, Storm } from '../api/types';
import { useUiStore } from '../state/uiStore';
import { useEntitlements, useVisibleCrises } from '../state/queries';
import { isLiteDevice } from '../lite';
import { syncBaseLayers } from './baseLayers';
import {
  addCrisisLayers,
  attachCrisisInteractions,
  escapeHtml,
  hitsCrisisLayer,
  removeCrisisLayers,
  setCrisisData,
} from './crisisLayers';
import { addTimezoneLayer, removeTimezoneLayer, timezonePopupHtml, TIMEZONE_HIT_LAYER_ID } from './TimezoneLayer';
import { isOnNearHemisphere } from './hemisphere';

// Real, current OpenFreeMap style URL (no API key required).
// See https://openfreemap.org/quick_start/ — "liberty" is OpenFreeMap's full-detail style.
const OPENFREEMAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

// MapLibre's worker file (maplibre-gl-worker.mjs) internally does a plain ES
// `import ... from "./maplibre-gl-shared.mjs"` against its OWN published dist
// files — Vite's automatic worker-chunking (triggered by MapLibre's internal
// `new Worker(new URL(...))` call) emits the worker chunk itself but does not
// follow that further nested import, so the production build silently ships
// a worker file whose own import 404s (Flask's SPA fallback then serves
// index.html for it, which the browser correctly rejects as "not a JS
// module"). Confirmed live: this broke tile/label processing (a washed-out
// white globe) only in the production build, not the Vite dev server.
// Fix: serve MapLibre's real, unmodified worker + its shared chunk as plain
// static files (copied verbatim from node_modules/maplibre-gl/dist/ into
// public/) and point MapLibre at them explicitly, bypassing Vite's
// worker-bundling for this library entirely — the standard workaround for
// this known MapLibre+Vite integration issue.
maplibregl.setWorkerUrl('/maplibre-gl-worker.mjs');

// OpenFreeMap's "liberty" style (OpenMapTiles schema) only ships country
// BORDERS as thin `line` geometry in its `boundary` source-layer — verified
// live by fetching the style JSON — so there is no fill polygon to
// point-in-polygon test against for "which country did the user click".
// Real Natural Earth country polygons (same public-domain source
// OpenMapTiles itself is built from) are loaded as a separate, fully
// transparent fill layer purely for hit-testing via
// queryRenderedFeatures — never rendered visibly.
const COUNTRY_BOUNDARIES_URL =
  'https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector/geojson/ne_110m_admin_0_countries.geojson';
const COUNTRY_HIT_SOURCE_ID = 'country-hit-test';
const COUNTRY_HIT_LAYER_ID = 'country-hit-test-fill';

export default function Globe() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  // Storm pins only — crisis pins are a GPU layer (see crisisLayers.ts).
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const selectCountry = useUiStore((s) => s.selectCountry);
  const activeMode = useUiStore((s) => s.activeMode);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const scope = useUiStore((s) => s.scope);
  const timeRange = useUiStore((s) => s.timeRange);
  const { data: crises } = useVisibleCrises(scope, timeRange);
  const satellite = useUiStore((s) => s.satellite);
  const relief = useUiStore((s) => s.relief);
  const { premium } = useEntitlements();
  const selectCrisisRef = useRef(selectCrisis);
  const selectCountryRef = useRef(selectCountry);
  const activeModeRef = useRef(activeMode);
  selectCrisisRef.current = selectCrisis;
  selectCountryRef.current = selectCountry;
  activeModeRef.current = activeMode;
  const crisesByIdRef = useRef(new Map<string, CrisisSummary>());
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OPENFREEMAP_STYLE_URL,
      center: [15, 20],
      zoom: 1.5,
      // Phones report a 3x pixel ratio; rendering the globe at 3x is a ~2.25x
      // fill-rate cost over 2x for no visible gain on a map.
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }));

    map.on('style.load', () => {
      // Real, documented MapLibre v5+ globe projection API.
      map.setProjection({ type: 'globe' });

      // Invisible hit-test layer for "click a country" (see comment above
      // COUNTRY_BOUNDARIES_URL — the base style has no fill polygon to
      // query against). Added on every style.load since MapLibre clears
      // custom sources/layers on a style change.
      if (!map.getSource(COUNTRY_HIT_SOURCE_ID)) {
        map.addSource(COUNTRY_HIT_SOURCE_ID, {
          type: 'geojson',
          data: COUNTRY_BOUNDARIES_URL,
        });
        map.addLayer({
          id: COUNTRY_HIT_LAYER_ID,
          type: 'fill',
          source: COUNTRY_HIT_SOURCE_ID,
          paint: { 'fill-color': '#000000', 'fill-opacity': 0 },
        });
      }
    });

    map.on('load', () => {
      setMapReady(true);

      // Item 10.6 — real draw/measure tool (point/line/polygon/rectangle/
      // circle/freehand), with real Turf-computed distance/area labels built
      // into the plugin's own MaplibreMeasureControl. Added as a standard
      // MapLibre IControl (like NavigationControl above) — it renders its own
      // toggle button + toolbar, so no extra React UI is needed. Placed
      // bottom-right (away from NavigationControl's top-right zoom buttons and
      // ModeSwitcher's top-center cluster). Loaded after the map is up (a
      // separate chunk) so terra-draw/Turf stay off the critical path.
      import('./DrawMeasureControl').then(({ createDrawMeasureControl }) => {
        if (mapRef.current === map) map.addControl(createDrawMeasureControl(), 'bottom-right');
      });
    });

    // Country click: must yield to a crisis pin/cluster under the cursor —
    // MapLibre fires each layer's click handler independently, so without
    // the hitsCrisisLayer check a pin click would ALSO select the country
    // beneath it and overwrite the event selection (storm markers are DOM
    // elements that stopPropagation themselves, so they never reach here).
    // Guarded by activeModeRef so a Time Zone-mode click on a country's
    // territory doesn't ALSO select that country and force-open the
    // country Analysis view underneath the timezone popup — the two
    // invisible hit-test fill layers otherwise sit on top of each other.
    map.on('click', COUNTRY_HIT_LAYER_ID, (e) => {
      if (activeModeRef.current !== 'events' && activeModeRef.current !== 'weather') return;
      if (hitsCrisisLayer(map, e.point)) return;
      const feature = e.features?.[0];
      const props = feature?.properties as Record<string, unknown> | undefined;
      const iso2 = (props?.ISO_A2 as string | undefined) ?? (props?.ISO_A2_EH as string | undefined);
      if (iso2 && iso2 !== '-99') {
        selectCountryRef.current(iso2);
      }
    });

    map.on('mouseenter', COUNTRY_HIT_LAYER_ID, () => {
      if (activeModeRef.current !== 'events' && activeModeRef.current !== 'weather') return;
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', COUNTRY_HIT_LAYER_ID, () => {
      map.getCanvas().style.cursor = '';
    });

    // Item 10.9: storm pins are plain screen-projected DOM markers, not
    // real 3D-occluded objects, so on a globe projection a far-hemisphere
    // marker would otherwise render on top of the globe's own surface.
    // `move` fires continuously during pan/rotate/zoom. Only the handful of
    // storm markers go through this now — crisis pins are a GPU layer that
    // the globe projection occludes itself — so it's cheap.
    map.on('move', () => updateMarkerVisibility(map, markersRef.current));

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  // Re-render pins whenever the map finishes loading or the globe mode
  // changes. Switching modes only changes what's rendered on the globe —
  // it never touches the sidebars/pinned Analysis selection (handled
  // entirely in uiStore.setActiveMode).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    let cancelled = false;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // TimezoneLayer is a map source/layer (not a DOM marker), so it's
    // always removed on mode change regardless of which mode is active,
    // then re-added only for 'timezone'.
    removeTimezoneLayer(map);

    let timezoneClickHandler: ((e: maplibregl.MapLayerMouseEvent) => void) | null = null;
    let timezonePopup: maplibregl.Popup | null = null;
    const timezoneEnterHandler = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const timezoneLeaveHandler = () => {
      map.getCanvas().style.cursor = '';
    };

    if (activeMode === 'weather') {
      fetchActiveStorms()
        .then((res) => {
          if (cancelled) return;
          addStormMarkers(map, res.storms, markersRef);
          updateMarkerVisibility(map, markersRef.current);
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.error('Failed to load active storms:', err);
        });
    } else if (activeMode === 'timezone') {
      addTimezoneLayer(map);
      map.getCanvas().style.cursor = '';
      timezoneClickHandler = (e) => {
        const feature = e.features?.[0];
        const tzid = feature?.properties?.tzid as string | undefined;
        if (!tzid) return;
        timezonePopup?.remove();
        timezonePopup = new maplibregl.Popup({ offset: 8 })
          .setLngLat(e.lngLat)
          .setHTML(timezonePopupHtml(tzid))
          .addTo(map);
      };
      map.on('click', TIMEZONE_HIT_LAYER_ID, timezoneClickHandler);
      map.on('mouseenter', TIMEZONE_HIT_LAYER_ID, timezoneEnterHandler);
      map.on('mouseleave', TIMEZONE_HIT_LAYER_ID, timezoneLeaveHandler);
    }

    return () => {
      cancelled = true;
      if (timezoneClickHandler) {
        map.off('click', TIMEZONE_HIT_LAYER_ID, timezoneClickHandler);
        map.off('mouseenter', TIMEZONE_HIT_LAYER_ID, timezoneEnterHandler);
        map.off('mouseleave', TIMEZONE_HIT_LAYER_ID, timezoneLeaveHandler);
      }
      timezonePopup?.remove();
    };
  }, [activeMode, mapReady]);

  // Premium layers (satellite imagery, topography). Premium is required here
  // too — not just in the UI — so stale toggle state can never render a
  // layer for a non-premium user. 3D terrain is skipped on phones/low-core
  // devices; they get the shaded relief only.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncBaseLayers(map, {
      satellite: premium && satellite,
      relief: premium && relief,
      terrain3d: !isLiteDevice(),
    });
  }, [mapReady, premium, satellite, relief]);

  // Crisis pins: layers exist only in Events mode; their data follows the
  // shared query (so scope/range changes just swap the source's data).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || activeMode !== 'events') return;
    addCrisisLayers(map);
    const detach = attachCrisisInteractions(map, {
      getById: (id) => crisesByIdRef.current.get(id),
      onSelect: (crisis) => selectCrisisRef.current(crisis),
    });
    return () => {
      detach();
      removeCrisisLayers(map);
    };
  }, [activeMode, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || activeMode !== 'events') return;
    crisesByIdRef.current = new Map((crises ?? []).map((c) => [c.id, c]));
    setCrisisData(map, crises ?? []);
  }, [crises, activeMode, mapReady]);

  // Item 10.5: center the camera on a crisis pin whenever it becomes the
  // pinned selection. Implemented as a subscription to the shared
  // `pinnedSelection` store state (set by `selectCrisis`/`selectCountry`)
  // rather than a camera call inside each click handler that can trigger a
  // selection (a pin here, a list item in EventsSidebar.tsx, a stack-popup
  // row), so every current and future path that calls `selectCrisis`
  // centers the pin for free.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!pinnedSelection || pinnedSelection.kind !== 'event') return;
    const { crisis } = pinnedSelection;
    if (typeof crisis.lat !== 'number' || typeof crisis.lon !== 'number') return;

    // Center only — never change the zoom. easeTo pans straight to the pin
    // at the current zoom (flyTo would also arc the zoom in/out en route,
    // and a fixed target zoom zoomed OUT anyone already closer than it).
    map.easeTo({
      center: [crisis.lon, crisis.lat],
      essential: true,
    });
  }, [pinnedSelection, mapReady]);

  return (
    <div
      ref={containerRef}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    />
  );
}

// Storm pins use a visually distinct marker (a solid triangle/spiral-ish
// diamond in cyan-blue, vs. crisis pins' circular severity-colored dots)
// so Weather mode is immediately distinguishable from Events mode, per the
// plan's "pins used to pin point catastrophic storms" ask. For this step
// clicking a pin just shows a real-data popup (name/category/date) — no
// dedicated StormAnalysis sidebar view.
function addStormMarkers(
  map: maplibregl.Map,
  storms: Storm[],
  markersRef: React.MutableRefObject<maplibregl.Marker[]>,
) {
  storms.forEach((storm) => {
    if (typeof storm.lat !== 'number' || typeof storm.lon !== 'number') return;

    const el = document.createElement('div');
    el.style.width = '14px';
    el.style.height = '14px';
    el.style.transform = 'rotate(45deg)';
    el.style.backgroundColor = colorForAlertLevel(storm.alert_level);
    el.style.border = '1px solid rgba(255,255,255,0.9)';
    el.style.cursor = 'pointer';
    el.style.boxShadow = '0 0 6px rgba(0,150,255,0.7)';

    const category = storm.severity_text ?? 'Unknown category';
    const dateLabel = storm.from_date ? new Date(storm.from_date).toLocaleDateString() : 'unknown date';

    // Same stopPropagation reasoning as crisis markers — Weather mode keeps
    // the country hit-test layer active, so an unguarded storm-pin click
    // would also silently force-open a country Analysis selection.
    el.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([storm.lon, storm.lat])
      .setPopup(
        new maplibregl.Popup({ offset: 12 }).setHTML(
          `<strong>${escapeHtml(storm.name ?? 'Unnamed storm')}</strong><br/>${escapeHtml(category)}<br/>Since ${escapeHtml(dateLabel)}`,
        ),
      )
      .addTo(map);

    markersRef.current.push(marker);
  });
}

// Item 10.9: shared far-hemisphere visibility helper, applied to both
// crisis pins and storm pins (and any future marker type) from one place
// rather than duplicated per-marker-type logic. Reads each marker's real
// lng/lat straight off the maplibregl.Marker instance (`getLngLat()`) so
// there's no separate lng/lat bookkeeping to keep in sync with the markers
// array itself.
function updateMarkerVisibility(map: maplibregl.Map, markers: maplibregl.Marker[]) {
  const center = map.getCenter();
  const centerPoint: [number, number] = [center.lng, center.lat];

  markers.forEach((marker) => {
    const lngLat = marker.getLngLat();
    const near = isOnNearHemisphere(centerPoint, [lngLat.lng, lngLat.lat]);
    marker.getElement().style.display = near ? '' : 'none';
  });
}

function colorForAlertLevel(level: string | null): string {
  switch (level) {
    case 'Red':
      return '#ff2d55';
    case 'Orange':
      return '#ff9500';
    default:
      return '#0ac8ff';
  }
}
