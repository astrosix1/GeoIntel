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

  // --- Visibility: WHETHER each sidebar is shown. Purely hover/click
  // driven (useHoverZone.ts), independent of `pinnedSelection`.
  leftOpen: boolean;
  rightOpen: boolean;
  setLeftOpen: (open: boolean) => void;
  setRightOpen: (open: boolean) => void;

  // Hover sources that feed the derived leftOpen/rightOpen state in
  // useHoverZone.ts: the visible edge tab handles (10.3) and each panel's
  // own rendered content (the pre-existing "panel-hover fusion" pattern —
  // keeps a panel open while the cursor is over it, not just its tab).
  leftEdgeHovered: boolean;
  rightEdgeHovered: boolean;
  leftPanelHovered: boolean;
  rightPanelHovered: boolean;
  setLeftEdgeHovered: (hovered: boolean) => void;
  setRightEdgeHovered: (hovered: boolean) => void;
  setLeftPanelHovered: (hovered: boolean) => void;
  setRightPanelHovered: (hovered: boolean) => void;

  // A plain click on an edge tab also toggles its sidebar open (10.3,
  // accessibility beyond pure hover) independent of hover state.
  leftManualOpen: boolean;
  rightManualOpen: boolean;
  toggleLeftManual: () => void;
  toggleRightManual: () => void;

  // Hovering the globe/map canvas force-closes both sidebars immediately
  // and unconditionally (10.2, rule 3) — this resets every hover/manual
  // source, not just the derived open flags, so a stale hover flag can't
  // silently reopen a panel on the next state change.
  forceCloseAll: () => void;

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

  leftEdgeHovered: false,
  rightEdgeHovered: false,
  leftPanelHovered: false,
  rightPanelHovered: false,
  setLeftEdgeHovered: (hovered) => set({ leftEdgeHovered: hovered }),
  setRightEdgeHovered: (hovered) => set({ rightEdgeHovered: hovered }),
  setLeftPanelHovered: (hovered) => set({ leftPanelHovered: hovered }),
  setRightPanelHovered: (hovered) => set({ rightPanelHovered: hovered }),

  leftManualOpen: false,
  rightManualOpen: false,
  toggleLeftManual: () => set((s) => ({ leftManualOpen: !s.leftManualOpen })),
  toggleRightManual: () => set((s) => ({ rightManualOpen: !s.rightManualOpen })),

  forceCloseAll: () =>
    set({
      leftOpen: false,
      rightOpen: false,
      leftEdgeHovered: false,
      rightEdgeHovered: false,
      leftPanelHovered: false,
      rightPanelHovered: false,
      leftManualOpen: false,
      rightManualOpen: false,
    }),

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
