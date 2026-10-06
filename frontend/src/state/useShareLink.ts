import { useEffect, useRef } from 'react';
import { clearShareParams, parseShareTarget } from '../lib/shareLink';
import type { ShareTarget } from '../lib/shareLink';
import { useStormsQuery } from './queries';
import { useUiStore } from './uiStore';

// Applies a shared Weather link (?view=weather&hazard=TC-123 or &lat=..&lon=..) once, on load.
// A point opens straight away; a hazard waits for the active list and, if that hazard has since
// ended, simply opens Weather mode (it is no longer on the map to select).
export function useShareLink() {
  const target = useRef<ShareTarget | null | undefined>(undefined);
  if (target.current === undefined) target.current = parseShareTarget(window.location.search);
  const pending = target.current;

  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectPoint = useUiStore((s) => s.selectPoint);
  const selectHazard = useUiStore((s) => s.selectHazard);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const setLeftOpen = useUiStore((s) => s.setLeftOpen);
  const setWeatherNotice = useUiStore((s) => s.setWeatherNotice);
  const selectZone = useUiStore((s) => s.selectZone);
  const showSharedClocks = useUiStore((s) => s.showSharedClocks);
  const setZoneNotice = useUiStore((s) => s.setZoneNotice);
  const applied = useRef(false);
  const { data, isError } = useStormsQuery(pending?.kind === 'hazard');

  useEffect(() => {
    if (!pending || applied.current) return;
    if (pending.kind === 'zone' || pending.kind === 'clocks' || pending.kind === 'invalid') {
      applied.current = true;
      setActiveMode('timezone');
      if (pending.kind === 'zone') {
        selectZone(pending.tzid);
        setRightOpen(true);
      } else if (pending.kind === 'clocks') {
        showSharedClocks(pending.zones);
        setLeftOpen(true);
        if (pending.skipped > 0) {
          setZoneNotice(`${pending.skipped} place${pending.skipped === 1 ? '' : 's'} in that link ${pending.skipped === 1 ? 'was' : 'were'} left out (not a recognised time zone, or beyond the limit of 8).`);
        }
      } else {
        setZoneNotice(pending.message);
      }
      clearShareParams();
      return;
    }
    if (pending.kind === 'point') {
      applied.current = true;
      setActiveMode('weather');
      selectPoint(pending.lat, pending.lon, pending.label);
      setRightOpen(true);
      clearShareParams();
      return;
    }
    if (pending.kind !== 'hazard') return;
    if (!data && !isError) return;       // still loading the active hazards
    applied.current = true;
    setActiveMode('weather');
    const storm = data?.storms.find((s) => s.event_type === pending.eventType && s.id === pending.id);
    if (storm) {
      selectHazard(storm);
      setRightOpen(true);
    } else if (data) {
      setWeatherNotice('That hazard is no longer active, so it is not on the map.');
    } else {
      setWeatherNotice("Live hazard data isn't available right now, so the shared hazard could not be opened.");
    }
    clearShareParams();
  }, [pending, data, isError, setActiveMode, selectPoint, selectHazard, setRightOpen, setLeftOpen, setWeatherNotice, selectZone, showSharedClocks, setZoneNotice]);
}
