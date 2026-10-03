import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { CrisisScope } from '../api/client';
import { TIME_RANGE_DAYS } from './uiStore';
import type { TimeRange } from './uiStore';
import { fetchCrises, fetchCrisisBriefing, fetchCrisisDetail, fetchCountryProfile, fetchMe } from '../api/client';
import { getAccessToken } from '../auth/session';

export interface Entitlements {
  signedIn: boolean;
  premium: boolean;
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
  return { signedIn: data?.signedIn ?? false, premium: data?.premium ?? false, loading: isLoading };
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

export function useCountryProfileQuery(countryCode: string | undefined) {
  return useQuery({
    queryKey: ['country-profile', countryCode],
    queryFn: () => fetchCountryProfile(countryCode as string),
    enabled: !!countryCode,
    staleTime: 6 * 60 * 60 * 1000, // matches the backend's own 6h cache TTL
  });
}
