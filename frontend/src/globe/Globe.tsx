import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { CrisisSummary, Storm } from '../api/types';
import { useUiStore } from '../state/uiStore';
import { useEntitlements, useHazardDetailQuery, useStormsQuery, useVisibleCrises, useWatchQuery } from '../state/queries';
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
import { clearNight, setNight } from './nightLayer';
import { clearZoneLabels, setZoneLabels } from './zoneLabelLayer';
import { loadZoneGeoJson } from '../lib/zoneLookup';
import { labelPoints } from '../lib/zoneLabels';
import type { LabelPoint } from '../lib/zoneLabels';
import { addTimezoneLayer, removeTimezoneLayer, timezonePopupHtml, TIMEZONE_HIT_LAYER_ID } from './TimezoneLayer';
import { isOnNearHemisphere } from './hemisphere';
import { ALERT_COLORS, hazardIcon } from './hazards';
import { useRadar } from './useRadar';
import { applyCrisisFilter, applyHazardFilter } from '../lib/filters';
import { clearHazardGeometry, setHazardGeometry } from './hazardGeometry';
import { useReportedAtNight } from '../state/useZoneIndex';

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
  const selectHazard = useUiStore((s) => s.selectHazard);
  const selectPoint = useUiStore((s) => s.selectPoint);
  const selectZone = useUiStore((s) => s.selectZone);
  const nightOn = useUiStore((s) => s.nightOn);
  const zoneLabelsOn = useUiStore((s) => s.zoneLabelsOn);
  const [labelPts, setLabelPts] = useState<LabelPoint[]>([]);
  const timeOffset = useUiStore((s) => s.timeOffsetMinutes);
  const weatherTab = useUiStore((s) => s.weatherTab);
  const weatherCategory = useUiStore((s) => s.weatherCategory);
  const eventsTab = useUiStore((s) => s.eventsTab);
  const activeCategory = useUiStore((s) => s.activeCategory);
  const activeMode = useUiStore((s) => s.activeMode);
  const pinnedSelection = useUiStore((s) => s.pinnedSelection);
  const scope = useUiStore((s) => s.scope);
  const timeRange = useUiStore((s) => s.timeRange);
  const { data: crises } = useVisibleCrises(scope, timeRange);
  const nightIds = useReportedAtNight(crises).ids;
  const { data: stormData } = useStormsQuery(activeMode === 'weather');
  const { data: watchData } = useWatchQuery();
  const selectedHazard = pinnedSelection?.kind === 'hazard' ? pinnedSelection.hazard : null;
  const { data: hazardDetail } = useHazardDetailQuery(
    activeMode === 'weather' && selectedHazard ? selectedHazard.event_type : null,
    activeMode === 'weather' && selectedHazard ? selectedHazard.id : null,
  );
  const satellite = useUiStore((s) => s.satellite);
  const relief = useUiStore((s) => s.relief);
  const { premium } = useEntitlements();
  const selectCrisisRef = useRef(selectCrisis);
  const selectCountryRef = useRef(selectCountry);
  const selectHazardRef = useRef(selectHazard);
  const selectPointRef = useRef(selectPoint);
  const pointMarkerRef = useRef<maplibregl.Marker | null>(null);
  const placeMarkersRef = useRef<maplibregl.Marker[]>([]);
  const stormPopupRef = useRef<maplibregl.Popup | null>(null);
  const activeModeRef = useRef(activeMode);
  selectCrisisRef.current = selectCrisis;
  selectCountryRef.current = selectCountry;
  selectHazardRef.current = selectHazard;
  selectPointRef.current = selectPoint;
  activeModeRef.current = activeMode;
  // Events behind each location pin (several can share one coordinate).
  const crisisGroupsRef = useRef(new Map<string, CrisisSummary[]>());
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
      // Weather mode uses the click for a point forecast instead (below).
      if (activeModeRef.current !== 'events') return;
      if (hitsCrisisLayer(map, e.point)) return;
      const feature = e.features?.[0];
      const props = feature?.properties as Record<string, unknown> | undefined;
      const iso2 = (props?.ISO_A2 as string | undefined) ?? (props?.ISO_A2_EH as string | undefined);
      if (iso2 && iso2 !== '-99') {
        selectCountryRef.current(iso2);
      }
    });

    // Dragging the globe closes both side panels so the map has the whole
    // screen. Only a real drag (MapLibre's dragstart), never a plain click.
    map.on('dragstart', () => {
      const ui = useUiStore.getState();
      if (ui.leftOpen) ui.setLeftOpen(false);
      if (ui.rightOpen) ui.setRightOpen(false);
    });

    // Weather mode: a click anywhere that isn't a hazard pin (those stop the
    // click themselves) asks for the forecast at that spot. The panel opens
    // because showing the forecast is the whole point of the click. The country
    // name, when the point is on land, is just a friendlier title.
    map.on('click', (e) => {
      if (activeModeRef.current !== 'weather') return;
      let label: string | null = null;
      try {
        const hit = map.queryRenderedFeatures(e.point, { layers: [COUNTRY_HIT_LAYER_ID] })[0];
        const props = hit?.properties as Record<string, unknown> | undefined;
        label = (props?.NAME as string | undefined) ?? (props?.ADMIN as string | undefined) ?? null;
      } catch {
        /* hit-test layer not ready: no label */
      }
      selectPointRef.current(e.lngLat.lat, e.lngLat.lng, label);
      useUiStore.getState().setRightOpen(true);
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
    map.on('move', () => {
      updateMarkerVisibility(map, markersRef.current);
      if (pointMarkerRef.current) updateMarkerVisibility(map, [pointMarkerRef.current]);
      updateMarkerVisibility(map, placeMarkersRef.current);
    });

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

    if (activeMode === 'timezone') {
      addTimezoneLayer(map);
      map.getCanvas().style.cursor = '';
      timezoneClickHandler = (e) => {
        const feature = e.features?.[0];
        const tzid = feature?.properties?.tzid as string | undefined;
        if (!tzid) return;
        selectZone(tzid, { lat: e.lngLat.lat, lon: e.lngLat.lng });
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
      if (timezoneClickHandler) {
        map.off('click', TIMEZONE_HIT_LAYER_ID, timezoneClickHandler);
        map.off('mouseenter', TIMEZONE_HIT_LAYER_ID, timezoneEnterHandler);
        map.off('mouseleave', TIMEZONE_HIT_LAYER_ID, timezoneLeaveHandler);
      }
      timezonePopup?.remove();
    };
  }, [activeMode, mapReady, selectZone]);

  // Time Zone mode: the night side, redrawn each minute and whenever the time slider moves, and again
  // after a base-style change (which clears custom layers).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (activeMode !== 'timezone' || !nightOn) {
      clearNight(map);
      return;
    }
    const draw = () => setNight(map, new Date(Date.now() + timeOffset * 60_000));
    draw();
    const id = window.setInterval(draw, 60_000);
    map.on('style.load', draw);
    return () => {
      window.clearInterval(id);
      map.off('style.load', draw);
    };
  }, [activeMode, mapReady, nightOn, timeOffset]);

  // Time Zone mode: one point per zone for its time label, worked out once from the boundary file.
  useEffect(() => {
    if (activeMode !== 'timezone' || !zoneLabelsOn || labelPts.length > 0) return;
    let cancelled = false;
    loadZoneGeoJson().then((json) => {
      if (!cancelled && json) setLabelPts(labelPoints(json));
    });
    return () => {
      cancelled = true;
    };
  }, [activeMode, zoneLabelsOn, labelPts.length]);

  // Time Zone mode: each zone's time and offset on the map, following the time slider, redrawn each minute.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (activeMode !== 'timezone' || !zoneLabelsOn || labelPts.length === 0) {
      clearZoneLabels(map);
      return;
    }
    const draw = () => setZoneLabels(map, labelPts, new Date(Date.now() + timeOffset * 60_000));
    draw();
    const id = window.setInterval(draw, 60_000);
    map.on('style.load', draw);
    return () => {
      window.clearInterval(id);
      map.off('style.load', draw);
    };
  }, [activeMode, mapReady, zoneLabelsOn, labelPts, timeOffset]);

  useRadar(mapRef, mapReady);

  // Weather mode: one pin per active hazard (cyclone, flood, wildfire,
  // drought). Rebuilt when the data or the legend's filter changes; the mode
  // effect above already clears the markers when the mode itself changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || activeMode !== 'weather' || !stormData) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    const visible = applyHazardFilter(stormData.storms, weatherTab, weatherCategory);
    addStormMarkers(map, visible, markersRef, stormPopupRef, (storm) => selectHazardRef.current(storm));
    updateMarkerVisibility(map, markersRef.current);
    return () => {
      stormPopupRef.current?.remove();
      stormPopupRef.current = null;
    };
  }, [activeMode, mapReady, stormData, weatherTab, weatherCategory]);

  // Weather mode: the user's watchlist places (premium), as small labelled
  // squares so they stand apart from the round hazard badges.
  useEffect(() => {
    const map = mapRef.current;
    placeMarkersRef.current.forEach((m) => m.remove());
    placeMarkersRef.current = [];
    if (!map || !mapReady || activeMode !== 'weather' || !premium || !watchData) return;
    placeMarkersRef.current = watchData.places.map((place) => {
      const el = document.createElement('div');
      el.title = `${place.name} (watchlist, ${place.radius_km} km)`;
      el.setAttribute('aria-label', `Watchlist place: ${place.name}`);
      Object.assign(el.style, {
        width: '12px',
        height: '12px',
        background: '#fff',
        border: '3px solid #7c3aed',
        borderRadius: '3px',
        boxShadow: '0 0 6px rgba(0,0,0,0.6)',
        pointerEvents: 'auto',
      });
      return new maplibregl.Marker({ element: el }).setLngLat([place.lon, place.lat]).addTo(map);
    });
    updateMarkerVisibility(map, placeMarkersRef.current);
    return () => {
      placeMarkersRef.current.forEach((m) => m.remove());
      placeMarkersRef.current = [];
    };
  }, [activeMode, mapReady, premium, watchData]);

  // Weather mode: the selected hazard's track, wind zones, cone or affected area.
  // Redrawn after a base-style change (satellite, relief), which clears custom layers.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const show = activeMode === 'weather' && selectedHazard ? hazardDetail : null;
    const draw = () => (show ? setHazardGeometry(map, show) : clearHazardGeometry(map));
    draw();
    map.on('style.load', draw);
    return () => {
      map.off('style.load', draw);
    };
  }, [activeMode, mapReady, selectedHazard, hazardDetail]);

  // Weather mode: a dot where the forecast point was clicked.
  useEffect(() => {
    const map = mapRef.current;
    pointMarkerRef.current?.remove();
    pointMarkerRef.current = null;
    if (!map || !mapReady || activeMode !== 'weather' || pinnedSelection?.kind !== 'point') return;
    const el = document.createElement('div');
    Object.assign(el.style, {
      width: '14px',
      height: '14px',
      borderRadius: '50%',
      background: '#7dd3fc',
      border: '2px solid #fff',
      boxShadow: '0 0 0 3px rgba(125,211,252,0.35), 0 0 8px rgba(0,0,0,0.6)',
      pointerEvents: 'none',
    });
    pointMarkerRef.current = new maplibregl.Marker({ element: el })
      .setLngLat([pinnedSelection.lon, pinnedSelection.lat])
      .addTo(map);
    return () => {
      pointMarkerRef.current?.remove();
      pointMarkerRef.current = null;
    };
  }, [activeMode, mapReady, pinnedSelection]);

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
      getGroup: (key) => crisisGroupsRef.current.get(key),
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
    // The same All / Major / Categories filter the left-hand list applies.
    const shown = applyCrisisFilter(crises ?? [], eventsTab, activeCategory, nightIds);
    crisisGroupsRef.current = setCrisisData(map, shown);
  }, [crises, eventsTab, activeCategory, nightIds, activeMode, mapReady]);

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
    if (!pinnedSelection || (pinnedSelection.kind !== 'event' && pinnedSelection.kind !== 'hazard')) return;
    const crisis = pinnedSelection.kind === 'event' ? pinnedSelection.crisis : pinnedSelection.hazard;
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

// Weather pins: a round, alert-coloured badge with the hazard's icon, clearly
// different from Events mode's severity dots. Clicking one selects it (so the
// Analysis panel shows its details) and opens a small popup. MapLibre's own
// marker-popup toggle doesn't fire here because the click must not bubble to
// the map (it would also select the country underneath), so the popup is
// opened by hand and a single shared popup is reused.
function addStormMarkers(
  map: maplibregl.Map,
  storms: Storm[],
  markersRef: React.MutableRefObject<maplibregl.Marker[]>,
  popupRef: React.MutableRefObject<maplibregl.Popup | null>,
  onSelect: (storm: Storm) => void,
) {
  storms.forEach((storm) => {
    if (typeof storm.lat !== 'number' || typeof storm.lon !== 'number') return;
    const lngLat: [number, number] = [storm.lon, storm.lat];

    const el = document.createElement('button');
    el.type = 'button';
    el.textContent = hazardIcon(storm.event_type);
    el.setAttribute('aria-label', `${storm.hazard ?? 'Weather event'}: ${storm.name ?? 'unnamed'}`);
    Object.assign(el.style, {
      width: '24px',
      height: '24px',
      padding: '0',
      borderRadius: '50%',
      fontSize: '13px',
      lineHeight: '22px',
      textAlign: 'center',
      cursor: 'pointer',
      background: colorForAlertLevel(storm.alert_level),
      border: '1.5px solid rgba(255,255,255,0.9)',
      boxShadow: '0 0 6px rgba(0,0,0,0.5)',
    });

    el.addEventListener('click', (e) => {
      e.stopPropagation();
      onSelect(storm);
      popupRef.current?.remove();
      popupRef.current = new maplibregl.Popup({ offset: 14, closeButton: false })
        .setLngLat(lngLat)
        .setHTML(
          `<strong>${escapeHtml(storm.name ?? storm.hazard ?? 'Weather event')}</strong><br/>` +
            `${escapeHtml(storm.hazard ?? '')}${storm.alert_level ? ` · ${escapeHtml(storm.alert_level)} alert` : ''}`,
        )
        .addTo(map);
    });

    markersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map));
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
  return ALERT_COLORS[level ?? 'Unknown'] ?? ALERT_COLORS.Unknown;
}
