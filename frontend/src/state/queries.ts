import { useMemo } from 'react';
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CrisisScope } from '../api/client';
import { TIME_RANGE_DAYS } from './uiStore';
import type { TimeRange } from './uiStore';
import type { CrisisDetail, CrisisSummary, ReportReason } from '../api/types';
import {
  deleteComment,
  addWatchPlace,
  deleteWatchPlace,
  fetchActiveStorms,
  fetchHazardDetail,
  fetchEventHazards,
  fetchEventAnalysis,
  fetchHazardEvents,
  fetchAlertSettings,
  fetchAlerts,
  fetchWatch,
  markAlertsRead,
  refineCrisisLocation,
  saveAlertSettings,
  searchPlaces,
  fetchForecast,
  fetchRadarFrames,
  fetchComments,
  fetchProfile,
  postComment,
  reportComment,
  saveProfile,
  fetchCrises,
  fetchCrisisBriefing,
  fetchCrisisDetail,
  fetchCountryTab,
  fetchWeatherLayers,
  fetchCountryTabRead,
  fetchCountryProfile,
  fetchCrisisScenarios,
  fetchMe,
  fetchPrefs,
  fetchSaved,
  saveEvent,
  savePrefs,
  unsaveEvent,
} from '../api/client';
import { outletOf } from '../lib/outlet';
import { getAccessToken, isDemoPremium } from '../auth/session';

export interface Entitlements {
  signedIn: boolean;
  premium: boolean;
  // Premium, or the backend's testing switch is on: features that need no account of their own are open.
  unlocked: boolean;
  loading: boolean;
}

// Drives every locked/unlocked UI state. Defaults to anonymous/free while
// loading or if /api/me fails, so a backend hiccup can only ever lock things,
// never unlock them (the server enforces premium regardless).
export function useEntitlements(): Entitlements {
  const { data, isLoading } = useQuery({
    queryKey: ['me', getAccessToken() ?? 'anonymous'],
    queryFn: fetchMe,
    staleTime: 60_000,
    retry: false,
  });
  // Dev-server-only demo switch (see auth/session.ts); always false in production.
  if (isDemoPremium()) return { signedIn: true, premium: true, unlocked: true, loading: false };
  const premium = data?.premium ?? false;
  return { signedIn: data?.signedIn ?? false, premium, unlocked: premium || (data?.openAccess ?? false), loading: isLoading };
}

// One shared query feeds both the globe pins and the Events list, so the
// (large) list is fetched once. Keeping the previous result while a new
// scope/range loads avoids blanking the globe on every toggle.
export function useCrisesQuery(scope: CrisisScope, range: TimeRange) {
  return useQuery({
    queryKey: ['crises', scope, range],
    queryFn: () => fetchCrises({ scope, days: TIME_RANGE_DAYS[range] }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

// ---- Premium dashboard data. Server state, fetched only for premium users, and
// never refetched behind the user's back (each is a call to our own API that
// the user explicitly changes via the UI).
export function useSavedEventsQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['saved-events'],
    queryFn: fetchSaved,
    enabled: premium,
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useSaveEventMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, save }: { id: string; save: boolean }) => {
      if (save) await saveEvent(id);
      else await unsaveEvent(id);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-events'] }),
  });
}

export function usePrefsQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['user-prefs'],
    queryFn: fetchPrefs,
    enabled: premium,
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useUpdatePrefsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (hiddenOutlets: string[]) => savePrefs(hiddenOutlets),
    onSuccess: (prefs) => queryClient.setQueryData(['user-prefs'], prefs),
  });
}

// The crisis list as the user wants to see it: the shared query minus events
// from outlets they've hidden (premium only). The Events list, its count and
// the globe all read this, so they always agree. Events with no source URL
// have no outlet and are never hidden.
export function useVisibleCrises(scope: CrisisScope, range: TimeRange) {
  const query = useCrisesQuery(scope, range);
  const { premium } = useEntitlements();
  const { data: prefs } = usePrefsQuery();
  const hidden = premium ? prefs?.hidden_outlets : undefined;
  const data = useMemo(() => {
    if (!query.data || !hidden || hidden.length === 0) return query.data;
    const hiddenSet = new Set(hidden);
    return query.data.filter((crisis) => {
      const outlet = outletOf(crisis.source_url);
      return !outlet || !hiddenSet.has(outlet);
    });
  }, [query.data, hidden]);
  return { ...query, data };
}

// ---- Event comments. Anyone can read; the token (when present) is sent so an
// author also sees their own auto-hidden comments. No refetch on focus.
export function useCommentsQuery(crisisId: string) {
  return useInfiniteQuery({
    queryKey: ['comments', crisisId],
    queryFn: ({ pageParam }) => fetchComments(crisisId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before ?? undefined,
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function usePostCommentMutation(crisisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => postComment(crisisId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['comments', crisisId] }),
  });
}

export function useDeleteCommentMutation(crisisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) => deleteComment(commentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['comments', crisisId] }),
  });
}

export function useReportCommentMutation() {
  return useMutation({
    mutationFn: ({ commentId, reason }: { commentId: string; reason: ReportReason }) =>
      reportComment(commentId, reason),
  });
}

export function useProfileQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['profile'],
    queryFn: fetchProfile,
    enabled: premium,
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useSaveProfileMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (displayName: string) => saveProfile(displayName),
    onSuccess: (profile) => queryClient.setQueryData(['profile'], profile),
  });
}

export function useCrisisDetailQuery(id: string | undefined) {
  return useQuery({
    queryKey: ['crisis', id],
    queryFn: () => fetchCrisisDetail(id as string),
    enabled: !!id,
  });
}

export function useCrisisBriefingQuery(id: string | undefined) {
  return useQuery({
    queryKey: ['crisis-briefing', id],
    queryFn: () => fetchCrisisBriefing(id as string),
    enabled: !!id,
  });
}

// Scenarios cost a paid AI call, so this only runs once the user asks
// (`enabled`) and the server caches the result for 12h; keep it just as long
// here so reopening an event doesn't refetch.
export function useCrisisScenariosQuery(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['crisis-scenarios', id],
    queryFn: () => fetchCrisisScenarios(id as string),
    enabled: !!id && enabled,
    retry: false,
    staleTime: 12 * 60 * 60 * 1000,
    // Every call is paid: never refetch behind the user's back (an errored
    // query counts as stale, so refocusing the tab would silently re-run it).
    // Retrying is the explicit "Try again" button.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useCountryProfileQuery(countryCode: string | undefined) {
  return useQuery({
    queryKey: ['country-profile', countryCode],
    queryFn: () => fetchCountryProfile(countryCode as string),
    enabled: !!countryCode,
    staleTime: 6 * 60 * 60 * 1000, // matches the backend's own 6h cache TTL
  });
}

// Premium country facts, one tab at a time (so a tab only loads its own data). Fetched once the viewer is unlocked and the tab is
// opened; the server enforces premium and caches each tab.
export function useCountryTabQuery(countryCode: string | undefined, tab: string, enabled: boolean) {
  return useQuery({
    queryKey: ['country-tab', countryCode, tab],
    queryFn: () => fetchCountryTab(countryCode as string, tab),
    enabled: !!countryCode && enabled,
    retry: false,
    staleTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// The analyst read costs a paid AI call, so it runs only when asked (`enabled`), is kept as long as the server keeps it (a week),
// and is never refetched behind the viewer's back.
export function useCountryReadQuery(countryCode: string | undefined, tab: string, enabled: boolean) {
  return useQuery({
    queryKey: ['country-read', countryCode, tab],
    queryFn: () => fetchCountryTabRead(countryCode as string, tab),
    enabled: !!countryCode && enabled,
    retry: false,
    staleTime: 7 * 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

// The forecast map layers and the times each can draw. Only asked for once a forecast layer is switched on; the server keeps
// the answer for half an hour.
export function useWeatherLayersQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['weather-layers'],
    queryFn: fetchWeatherLayers,
    enabled,
    retry: false,
    staleTime: 20 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// Weather mode's active hazards. Shared by the globe pins and the legend so
// they always agree; GDACS updates slowly, so a few minutes of staleness is fine.
export function useStormsQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['storms'],
    queryFn: fetchActiveStorms,
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// Track, footprint and exposure for one hazard. Shared by the map layers and the
// Analysis panel. GDACS revises these a few times a day.
export function useHazardDetailQuery(eventType: string | null, id: number | null) {
  return useQuery({
    queryKey: ['hazard-detail', eventType, id],
    queryFn: () => fetchHazardDetail(eventType as string, id as number),
    enabled: eventType !== null && id !== null,
    retry: false,
    staleTime: 15 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// Hazards whose footprint contains or is near an event, and events inside a hazard.
export function useEventHazardsQuery(crisisId: string | undefined) {
  return useQuery({
    queryKey: ['event-hazards', crisisId],
    queryFn: () => fetchEventHazards(crisisId as string),
    enabled: !!crisisId,
    retry: false,
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useEventAnalysisQuery(crisisId: string | undefined) {
  return useQuery({
    queryKey: ['event-analysis', crisisId],
    queryFn: () => fetchEventAnalysis(crisisId as string),
    enabled: !!crisisId,
    retry: false,
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useHazardEventsQuery(eventType: string | null, id: number | null) {
  return useQuery({
    queryKey: ['hazard-events', eventType, id],
    queryFn: () => fetchHazardEvents(eventType as string, id as number),
    enabled: eventType !== null && id !== null,
    retry: false,
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

// RainViewer's current radar frames (about two hours, 10 minutes apart).
// The list is republished every ~10 minutes, so poll at that pace while radar
// is showing.
export function useRadarFramesQuery(enabled: boolean) {
  return useQuery({
    queryKey: ['radar-frames'],
    queryFn: fetchRadarFrames,
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchInterval: enabled ? 10 * 60 * 1000 : false,
    refetchOnWindowFocus: false,
  });
}

// Point forecast for Weather mode. The server rounds to a 0.1 degree grid and
// caches 15 minutes, so a long staleTime here avoids pointless repeat calls.
export function useForecastQuery(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: ['forecast', lat, lon],
    queryFn: () => fetchForecast(lat as number, lon as number),
    enabled: lat !== null && lon !== null,
    retry: false,
    staleTime: 15 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

// ---- Watchlist places and hazard alerts (premium). No refetch on focus; the
// alerts query polls every 5 minutes so the unread badge stays current.
export function useWatchQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['watch'],
    queryFn: fetchWatch,
    enabled: premium,
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useAddPlaceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: addWatchPlace,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watch'] }),
  });
}

export function useDeletePlaceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteWatchPlace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watch'] });
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useAlertsQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['alerts'],
    queryFn: fetchAlerts,
    enabled: premium,
    retry: false,
    staleTime: 60_000,
    refetchInterval: premium ? 5 * 60_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
}

export function useMarkAlertsReadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAlertsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useAlertSettingsQuery() {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: ['alert-settings'],
    queryFn: fetchAlertSettings,
    enabled: premium,
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useSaveAlertSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveAlertSettings,
    onSuccess: (settings) => queryClient.setQueryData(['alert-settings'], settings),
  });
}

// Place-name search for the add-place form. Only runs for 2+ characters.
export function usePlaceSearch(query: string) {
  const { premium } = useEntitlements();
  const q = query.trim();
  return useQuery({
    queryKey: ['place-search', q.toLowerCase()],
    queryFn: () => searchPlaces(q),
    enabled: premium && q.length >= 2,
    retry: false,
    staleTime: 24 * 60 * 60_000,
    refetchOnWindowFocus: false,
  });
}

// Refine one event's pin from its article (premium). When the pin moves, the
// cached event lists are patched in place, so the globe updates without
// refetching the whole (large) list, and the detail cache is marked refined so
// the lookup isn't asked for again.
export function useRefineLocationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: refineCrisisLocation,
    onSuccess: (result, id) => {
      if (result.status === 'refined') {
        const { lat, lon } = result.location;
        queryClient.setQueriesData<CrisisSummary[]>({ queryKey: ['crises'] }, (list) =>
          list?.map((crisis) => (crisis.id === id ? { ...crisis, lat, lon } : crisis)),
        );
      }
      queryClient.setQueryData<CrisisDetail>(['crisis', id], (detail) =>
        detail
          ? {
              ...detail,
              ...(result.status === 'refined'
                ? { lat: result.location.lat, lon: result.location.lon, location_confidence: 90 }
                : {}),
              location_refined_name: result.status === 'refined' ? result.location.name : null,
              location_refined_at: new Date().toISOString(),
            }
          : detail,
      );
    },
  });
}
