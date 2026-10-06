import { useSyncExternalStore } from 'react';
import { create } from 'zustand';
import { loadTimeZone, loadUnits, saveTimeZone, saveUnits } from '../lib/units';
import type { TimeZoneMode, UnitSystem } from '../lib/units';
import { DOCK_MIN_WIDTH, loadMapView, loadPanels, loadStarfield, saveMapView, savePanels, saveStarfield } from '../ui/preferences';
import type { MapView, PanelsMode } from '../ui/preferences';
import { applyTheme, loadTheme, saveTheme } from '../ui/theme';
import type { ThemeChoice } from '../ui/theme';
import { useUiStore } from './uiStore';

// The Light theme is built into the tokens and shows in the component kit (?ui), but the app's own screens are
// converted to the tokens one stage at a time (docs/ui-redesign-plan.md). Until they all are, choosing Light in the
// app would leave unreadable panels, so the choice is offered but switched off. Flip this when the last screen is done.
export const LIGHT_THEME_READY = false;

interface SettingsState {
  panels: PanelsMode;
  starfield: boolean;
  mapView: MapView;
  theme: ThemeChoice;
  units: UnitSystem;
  timeZone: TimeZoneMode;
  setPanels: (mode: PanelsMode) => void;
  setStarfield: (on: boolean) => void;
  setMapView: (view: MapView) => void;
  setTheme: (choice: ThemeChoice) => void;
  setUnits: (units: UnitSystem) => void;
  setTimeZone: (mode: TimeZoneMode) => void;
}

export const useSettings = create<SettingsState>((set) => ({
  panels: loadPanels(),
  starfield: loadStarfield(),
  mapView: loadMapView(),
  theme: loadTheme(),
  units: loadUnits(),
  timeZone: loadTimeZone(),
  setPanels: (mode) => {
    savePanels(mode);
    set({ panels: mode });
    // Switching to docked shows the events panel straight away; switching back starts with both panels tucked away.
    const ui = useUiStore.getState();
    if (mode === 'docked') ui.setLeftOpen(true);
    else {
      ui.setLeftOpen(false);
      ui.setRightOpen(false);
    }
  },
  setStarfield: (on) => {
    saveStarfield(on);
    set({ starfield: on });
  },
  setMapView: (view) => {
    saveMapView(view);
    set({ mapView: view });
  },
  setTheme: (choice) => {
    saveTheme(choice);
    set({ theme: choice });
    applyTheme(LIGHT_THEME_READY ? choice : 'dark');
  },
  setUnits: (units) => {
    saveUnits(units);
    set({ units });
  },
  setTimeZone: (mode) => {
    saveTimeZone(mode);
    set({ timeZone: mode });
  },
}));

// Applied once at start-up (the component kit page applies the saved theme directly instead).
export function initAppTheme(): void {
  applyTheme(LIGHT_THEME_READY ? loadTheme() : 'dark');
}

const wide = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(`(min-width: ${DOCK_MIN_WIDTH}px)`) : null;

function subscribeWide(callback: () => void): () => void {
  wide?.addEventListener('change', callback);
  return () => wide?.removeEventListener('change', callback);
}

// True when the panels sit beside the map: the user chose Docked and the window is wide enough for it.
export function usePanelsDocked(): boolean {
  const panels = useSettings((s) => s.panels);
  const isWide = useSyncExternalStore(subscribeWide, () => wide?.matches ?? true, () => true);
  return panels === 'docked' && isWide;
}
