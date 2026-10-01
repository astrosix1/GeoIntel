import { create } from 'zustand';
import type { Crisis } from '../api/types';

// Globe mode switcher (steps 5-6 of the rewrite plan). 'events' shows
// crisis pins, 'weather' shows GDACS storm pins, 'timezone' shows real IANA
// timezone boundary lines with click-to-see-local-time (TimezoneLayer.tsx).
export type GlobeMode = 'events' | 'weather' | 'timezone';

// Discriminated union so AnalysisSidebar can hold either an event or a
// country selection in the same slot (step 4 of the rewrite plan).
export type PinnedSelection =
  | { kind: 'event'; crisis: Crisis }
  | { kind: 'country'; countryCode: string }
  | null;

export type EventsTab = 'all' | 'major' | 'categories';
export type CrisisScopeFilter = 'global' | 'local';

interface UiState {
  // --- Selection: WHAT to show in Analysis. Set by clicking a pin/country,
  // persists across mode changes and sidebar visibility changes until a
  // different one is clicked. Phase 10.2 explicitly decoupled this from
  // panel visibility — selecting something no longer force-opens or pins
  // the Analysis panel open.
  pinnedSelection: PinnedSelection;
  selectCrisis: (crisis: Crisis) => void;
  selectCountry: (countryCode: string) => void;
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

  // --- 10.1: Events sidebar All/Major/Categories tabs (client-side filter
  // over the already-fetched crisis list, no new request).
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

  eventsTab: 'all',
  activeCategory: null,
  setEventsTab: (tab) => set({ eventsTab: tab }),
  setActiveCategory: (category) => set({ activeCategory: category }),

  scope: 'global',
  setScope: (scope) => set({ scope }),
}));
