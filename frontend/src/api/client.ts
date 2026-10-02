import type { CrisesResponse, Crisis, CrisisDetail, Briefing, CountryProfile, Me, StormsResponse } from './types';
import { getAccessToken } from '../auth/session';

// In dev, requests go through Vite's proxy (see vite.config.ts) so they are
// same-origin and unaffected by the backend's CORS allowlist. In production,
// point this at the real backend origin via VITE_API_BASE_URL.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

// fetch() that attaches the user's Supabase token when signed in. Public
// endpoints keep using plain fetch(); use this for any account-aware or
// premium endpoint.
export function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

export async function fetchMe(): Promise<Me> {
  const res = await authedFetch('/api/me');
  if (!res.ok) {
    throw new Error(`Failed to fetch account status: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export type CrisisScope = 'global' | 'local' | 'all';

// `scope` is optional and omitted from the request entirely when not
// passed, so existing callers that don't care about local/global filtering
// (e.g. a future non-Events consumer) keep getting the unfiltered list.
export async function fetchCrises(scope?: CrisisScope): Promise<Crisis[]> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : '';
  const res = await fetch(`${API_BASE_URL}/api/crises${query}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch crises: ${res.status} ${res.statusText}`);
  }
  const data: CrisesResponse = await res.json();
  return data.crises;
}

export async function fetchCrisisDetail(id: string): Promise<CrisisDetail> {
  const res = await fetch(`${API_BASE_URL}/api/crises/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch crisis ${id}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchCrisisBriefing(id: string): Promise<Briefing> {
  const res = await fetch(`${API_BASE_URL}/api/crises/${encodeURIComponent(id)}/briefing`);
  if (!res.ok) {
    throw new Error(`Failed to fetch briefing for ${id}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchCountryProfile(countryCode: string): Promise<CountryProfile> {
  const res = await fetch(`${API_BASE_URL}/api/countries/${encodeURIComponent(countryCode)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch country profile for ${countryCode}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchActiveStorms(): Promise<StormsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/weather/storms`);
  if (!res.ok) {
    throw new Error(`Failed to fetch active storms: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
