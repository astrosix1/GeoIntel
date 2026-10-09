import { create } from 'zustand';
import type { CrisisSummary, Storm } from '../api/types';
import { cleanClocks, loadClockPrefs, loadClocks, MAX_CLOCKS, saveClockPrefs, saveClocks } from '../lib/clocks';
import type { ClockPrefs } from '../lib/timezones';
import { DEFAULT_CRISIS_SORT } from '../lib/filters';
import type { CrisisSort } from '../lib/filters';

// Globe mode switcher (steps 5-6 of the rewrite plan). 'events' shows
// crisis pins, 'weather' shows GDACS storm pins, 'timezone' shows real IANA
// timezone boundary lines with click-to-see-local-time (TimezoneLayer.tsx).
export type GlobeMode = 'events' | 'weather' | 'timezone';

// Discriminated union so AnalysisSidebar can hold either an event or a
// country selection in the same slot (step 4 of the rewrite plan).
export interface ComparePlace {
  lat: number;
  lon: number;
  label: string;
}

export const MAX_COMPARE_PLACES = 3;
// Time Zone mode can show the time up to a day either side of now.
export const MAX_TIME_OFFSET_MINUTES = 24 * 60;

export type PinnedSelection =
  | { kind: 'event'; crisis: CrisisSummary }
  | { kind: 'country'; countryCode: string }
  | { kind: 'hazard'; hazard: Storm }
  | { kind: 'point'; lat: number; lon: number; label: string | null }
  // `point` is where on the map the zone was clicked (for sunrise and sunset there), when it was a click.
  | { kind: 'zone'; tzid: string; point?: { lat: number; lon: number } }
  | null;

export type EventsTab = 'all' | 'major' | 'categories';
export type DashboardTab = 'saved' | 'sources' | 'watchlist' | 'alerts' | 'settings';

// A point picked from the forecast panel, waiting to be named and added to the watchlist.
export interface PendingWatchPoint {
  lat: number;
  lon: number;
  name: string;
}
export type CrisisScopeFilter = 'global' | 'local' | 'all';

// How far back the globe and Events list reach. GDELT adds ~11k events/day,
// so the default is the last 48h; 7d is server-capped to stay phone-friendly.
export type TimeRange = '24h' | '48h' | '7d';
export const TIME_RANGE_DAYS: Record<TimeRange, number> = { '24h': 1, '48h': 2, '7d': 7 };

interface UiState {
  // --- Selection: WHAT to show in Analysis. Set by clicking a pin/country,
  // persists across mode changes and sidebar visibility changes until a
  // different one is clicked. Phase 10.2 explicitly decoupled this from
  // panel visibility — selecting something no longer force-opens or pins
  // the Analysis panel open.
  pinnedSelection: PinnedSelection;
  selectCrisis: (crisis: CrisisSummary) => void;
  selectCountry: (countryCode: string) => void;
  selectHazard: (hazard: Storm) => void;
  selectPoint: (lat: number, lon: number, label: string | null) => void;
  selectZone: (tzid: string, point?: { lat: number; lon: number }) => void;
  clearPinnedSelection: () => void;

  // --- Visibility: WHETHER each sidebar is shown. `leftOpen`/`rightOpen`
  // are the sole source of truth — set directly by EdgeTab.tsx (hover-in
  // opens, a click toggles open/closed), independent of `pinnedSelection`.
  //
  // Previously this was re-derived on every hover-state change (edge-tab
  // hover OR panel-content hover OR a manual-open flag), with a separate
  // document-level listener that force-closed both sidebars the instant
  // the cursor touched the globe — even a second after deliberately
  // clicking a tab open. Confirmed directly with you this was the
  // "closing automatically" behavior to remove: once open, a sidebar now
  // stays open regardless of where the cursor goes, and the edge tab
  // itself becomes the close control (its chevron becomes an × — see
  // EdgeTab.tsx) rather than hovering elsewhere closing it for you.
  leftOpen: boolean;
  rightOpen: boolean;
  setLeftOpen: (open: boolean) => void;
  setRightOpen: (open: boolean) => void;

  activeMode: GlobeMode;
  setActiveMode: (mode: GlobeMode) => void;

  // Time Zone mode: the clocks the user pinned (zone ids, at most MAX_CLOCKS) and how clocks are shown.
  // Both are remembered in this browser only.
  clocks: string[];
  addClock: (tzid: string) => void;
  removeClock: (tzid: string) => void;
  // Clocks that arrived in a shared link are shown but not saved over the user's own until they choose to keep them.
  sharedClocks: boolean;
  showSharedClocks: (zones: string[]) => void;
  keepSharedClocks: () => void;
  // A one-line note in Time Zone mode (a shared link that could not be fully opened), and the map label switch.
  zoneNotice: string | null;
  setZoneNotice: (notice: string | null) => void;
  zoneLabelsOn: boolean;
  setZoneLabelsOn: (on: boolean) => void;
  clockPrefs: ClockPrefs;
  setClockPrefs: (prefs: ClockPrefs) => void;
  // Minutes from now that Time Zone mode is showing (0 = now), and whether the night side is shaded.
  timeOffsetMinutes: number;
  setTimeOffsetMinutes: (minutes: number) => void;
  nightOn: boolean;
  setNightOn: (on: boolean) => void;

  // A one-line note shown in Weather mode, for example when a shared link points at a hazard that has ended.
  weatherNotice: string | null;
  setWeatherNotice: (notice: string | null) => void;

  // Weather mode's All / Major / Categories filter (the same shape as the
  // Events one above, kept separate because the categories differ: here they
  // are GDACS hazard codes). Applied to both the list and the globe.
  weatherTab: EventsTab;
  weatherCategory: string | null;
  setWeatherTab: (tab: EventsTab) => void;
  setWeatherCategory: (category: string | null) => void;

  // Weather mode's radar overlay: on/off, playback, and the unix time of the
  // frame currently showing (null when radar isn't drawn).
  radarOn: boolean;
  // Forecast map layers (DWD ICON, one at a time), the forecast moment they show (unix ms; null = now), and the NASA satellite overlays.
  weatherField: 'temperature' | 'pressure' | 'rain' | 'wind' | null;
  forecastTime: number | null;
  cloudsOn: boolean;
  firesOn: boolean;
  setWeatherField: (field: 'temperature' | 'pressure' | 'rain' | 'wind' | null) => void;
  setForecastTime: (time: number | null) => void;
  setCloudsOn: (on: boolean) => void;
  setFiresOn: (on: boolean) => void;
  radarPlaying: boolean;
  radarTime: number | null;
  // Which radar frame is showing (an index into the frames in use; a number past the end means the newest) and the
  // times of those frames, for the radar timeline.
  radarCursor: number;
  radarFrameTimes: number[];
  setRadarCursor: (cursor: number) => void;
  setRadarFrameTimes: (times: number[]) => void;
  setRadarOn: (on: boolean) => void;
  setRadarPlaying: (playing: boolean) => void;
  setRadarTime: (time: number | null) => void;

  // --- 10.1: Events sidebar All/Major/Categories tabs (client-side filter
  // over the already-fetched crisis list, no new request).
  // Show only events first reported at night (22:00 to 05:00) at their own pin (Events mode, list and globe).
  reportedAtNight: boolean;
  setReportedAtNight: (on: boolean) => void;
  // How the events list is ordered (the globe is not affected).
  eventsSort: CrisisSort;
  setEventsSort: (sort: CrisisSort) => void;
  eventsTab: EventsTab;
  activeCategory: string | null;
  setEventsTab: (tab: EventsTab) => void;
  setActiveCategory: (category: string | null) => void;

  // --- 10.4 (frontend half): Local/Global scope toggle. Server-state
  // filter — passed as `?scope=` to the crisis-fetch, not a client-side
  // array filter, so the list and globe pins reflect what the backend
  // actually classified.
  scope: CrisisScopeFilter;
  setScope: (scope: CrisisScopeFilter) => void;

  // Server-side time window, like scope — changing it refetches.
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;

  // Premium globe layers (Phase 14). These are the user's *requests*; what
  // actually renders also requires premium (see Globe.tsx), so stale state
  // can never show a layer to a non-premium user.
  // "My dashboard" overlay (premium), opened from the account chip.
  dashboardOpen: boolean;
  dashboardTab: DashboardTab;
  setDashboardOpen: (open: boolean) => void;
  setDashboardTab: (tab: DashboardTab) => void;
  pendingWatchPoint: PendingWatchPoint | null;
  setPendingWatchPoint: (point: PendingWatchPoint | null) => void;

  // Weather mode: up to three places shown side by side (not saved anywhere).
  comparePlaces: ComparePlace[];
  addComparePlace: (place: ComparePlace) => void;
  removeComparePlace: (lat: number, lon: number) => void;
  clearComparePlaces: () => void;

  satellite: boolean;
  relief: boolean;
  setSatellite: (on: boolean) => void;
  setRelief: (on: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  pinnedSelection: null,
  // Clicking a pin/country only ever updates the selection now — it must
  // NOT touch leftOpen/rightOpen/leftManualOpen/rightManualOpen. Per the
  // product owner's explicit choice, if the cursor is over the globe right
  // after the click, Analysis still closes (forceCloseAll running from the
  // globe-hover listener) — this is intentional, not a bug.
  selectCrisis: (crisis) => set({ pinnedSelection: { kind: 'event', crisis } }),
  selectCountry: (countryCode) => set({ pinnedSelection: { kind: 'country', countryCode } }),
  selectHazard: (hazard) => set({ pinnedSelection: { kind: 'hazard', hazard } }),
  selectPoint: (lat, lon, label) => set({ pinnedSelection: { kind: 'point', lat, lon, label } }),
  selectZone: (tzid, point) => set({ pinnedSelection: { kind: 'zone', tzid, point } }),
  clearPinnedSelection: () => set({ pinnedSelection: null }),

  leftOpen: false,
  rightOpen: false,
  setLeftOpen: (open) => set({ leftOpen: open }),
  setRightOpen: (open) => set({ rightOpen: open }),

  activeMode: 'events',
  // Switching modes must NOT touch pinnedSelection or sidebar
  // visibility/hover state — it only changes what's rendered on the globe
  // itself (plan's explicit requirement).
  setActiveMode: (mode) => set({ activeMode: mode }),
  clocks: loadClocks(),
  addClock: (tzid) =>
    set((s) => {
      if (s.clocks.includes(tzid) || s.clocks.length >= MAX_CLOCKS) return s;
      const clocks = cleanClocks([...s.clocks, tzid]);
      saveClocks(clocks);
      return { clocks, sharedClocks: false };
    }),
  removeClock: (tzid) =>
    set((s) => {
      const clocks = s.clocks.filter((z) => z !== tzid);
      saveClocks(clocks);
      return { clocks, sharedClocks: false };
    }),
  timeOffsetMinutes: 0,
  setTimeOffsetMinutes: (minutes) =>
    set({ timeOffsetMinutes: Math.max(-MAX_TIME_OFFSET_MINUTES, Math.min(MAX_TIME_OFFSET_MINUTES, Math.round(minutes) || 0)) }),
  nightOn: true,
  setNightOn: (on) => set({ nightOn: on }),
  sharedClocks: false,
  showSharedClocks: (zones) => set({ clocks: cleanClocks(zones), sharedClocks: true }),
  keepSharedClocks: () =>
    set((s) => {
      saveClocks(s.clocks);
      return { sharedClocks: false };
    }),
  zoneNotice: null,
  setZoneNotice: (notice) => set({ zoneNotice: notice }),
  zoneLabelsOn: true,
  setZoneLabelsOn: (on) => set({ zoneLabelsOn: on }),
  clockPrefs: loadClockPrefs(),
  setClockPrefs: (prefs) => {
    saveClockPrefs(prefs);
    set({ clockPrefs: prefs });
  },
  weatherNotice: null,
  setWeatherNotice: (notice) => set({ weatherNotice: notice }),

  radarOn: true,
  weatherField: null,
  forecastTime: null,
  cloudsOn: false,
  firesOn: false,
  setWeatherField: (field) => set({ weatherField: field, forecastTime: null }),
  setForecastTime: (time) => set({ forecastTime: time }),
  setCloudsOn: (on) => set({ cloudsOn: on }),
  setFiresOn: (on) => set({ firesOn: on }),
  radarPlaying: true,
  radarTime: null,
  radarCursor: Number.MAX_SAFE_INTEGER,
  radarFrameTimes: [],
  setRadarCursor: (cursor) => set({ radarCursor: cursor }),
  setRadarFrameTimes: (times) => set({ radarFrameTimes: times }),
  setRadarOn: (on) => set({ radarOn: on }),
  setRadarPlaying: (playing) => set({ radarPlaying: playing }),
  setRadarTime: (time) => set({ radarTime: time }),

  weatherTab: 'all',
  weatherCategory: null,
  setWeatherTab: (tab) => set({ weatherTab: tab }),
  setWeatherCategory: (category) => set({ weatherCategory: category }),

  reportedAtNight: false,
  setReportedAtNight: (on) => set({ reportedAtNight: on }),
  eventsSort: DEFAULT_CRISIS_SORT,
  setEventsSort: (sort) => set({ eventsSort: sort }),
  eventsTab: 'all',
  activeCategory: null,
  setEventsTab: (tab) => set({ eventsTab: tab }),
  setActiveCategory: (category) => set({ activeCategory: category }),

  scope: 'global',
  setScope: (scope) => set({ scope }),

  timeRange: '48h',
  setTimeRange: (range) => set({ timeRange: range }),

  dashboardOpen: false,
  dashboardTab: 'saved',
  setDashboardOpen: (open) => set({ dashboardOpen: open }),
  setDashboardTab: (tab) => set({ dashboardTab: tab }),
  pendingWatchPoint: null,
  setPendingWatchPoint: (point) => set({ pendingWatchPoint: point }),
  comparePlaces: [],
  addComparePlace: (place) =>
    set((s) =>
      s.comparePlaces.length >= MAX_COMPARE_PLACES ||
      s.comparePlaces.some((p) => p.lat === place.lat && p.lon === place.lon)
        ? s
        : { comparePlaces: [...s.comparePlaces, place] },
    ),
  removeComparePlace: (lat, lon) => set((s) => ({ comparePlaces: s.comparePlaces.filter((p) => !(p.lat === lat && p.lon === lon)) })),
  clearComparePlaces: () => set({ comparePlaces: [] }),

  satellite: false,
  relief: false,
  setSatellite: (on) => set({ satellite: on }),
  setRelief: (on) => set({ relief: on }),
}));
