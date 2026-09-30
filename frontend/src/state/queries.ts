import { useQuery } from '@tanstack/react-query';
import type { CrisisScope } from '../api/client';
import { fetchCrises, fetchCrisisBriefing, fetchCrisisDetail, fetchCountryProfile } from '../api/client';

export function useCrisesQuery(scope?: CrisisScope) {
  return useQuery({
    queryKey: ['crises', scope ?? 'unfiltered'],
    queryFn: () => fetchCrises(scope),
    staleTime: 60_000,
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
