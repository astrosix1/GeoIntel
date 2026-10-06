import { useEffect, useMemo, useState } from 'react';
import type { CrisisSummary } from '../api/types';
import { CITY_LEVEL_CONFIDENCE, hasReportTime, reportedLocalTime } from '../lib/eventTime';
import { loadZoneIndex, zoneAt } from '../lib/zoneLookup';
import type { ZoneIndex } from '../lib/zoneLookup';
import { useUiStore } from './uiStore';

// The zone boundary file as a lookup index, fetched only once something asks for it.
export function useZoneIndex(enabled: boolean): ZoneIndex | null {
  const [index, setIndex] = useState<ZoneIndex | null>(null);
  useEffect(() => {
    if (!enabled || index) return;
    let cancelled = false;
    loadZoneIndex().then((loaded) => {
      if (!cancelled && loaded) setIndex(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, index]);
  return index;
}

export interface ReportedAtNight {
  // The ids to keep when the filter is on and ready; null means "do not filter" (off, or still loading).
  ids: Set<string> | null;
  loading: boolean;
  // Events the filter cannot judge: no time of day in their source, a coarse pin, or no zone found.
  excluded: number;
}

// Events whose first report appeared between 22:00 and 05:00 at their own pin, when the filter is switched on.
export function useReportedAtNight(crises: CrisisSummary[] | undefined): ReportedAtNight {
  const enabled = useUiStore((s) => s.reportedAtNight);
  const index = useZoneIndex(enabled);
  return useMemo(() => {
    if (!enabled) return { ids: null, loading: false, excluded: 0 };
    if (!index) return { ids: null, loading: true, excluded: 0 };
    const ids = new Set<string>();
    let excluded = 0;
    for (const crisis of crises ?? []) {
      const eligible = hasReportTime(crisis.id) && (crisis.location_confidence ?? 0) >= CITY_LEVEL_CONFIDENCE;
      const tzid = eligible ? zoneAt(index, crisis.lat, crisis.lon) : null;
      const reported = tzid ? reportedLocalTime(crisis.date, tzid, crisis.location_confidence) : null;
      if (!reported) excluded++;
      else if (reported.night) ids.add(crisis.id);
    }
    return { ids, loading: false, excluded };
  }, [enabled, index, crises]);
}
