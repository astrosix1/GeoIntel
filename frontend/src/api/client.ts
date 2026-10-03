import type { CrisesResponse, CrisisSummary, CrisisDetail, Briefing, CountryProfile, Me, StormsResponse } from './types';
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

export interface FetchCrisesOptions {
  scope?: CrisisScope;
  // Only events from the last N days. The backend ranks and caps longer
  // windows, so a request is always bounded.
  days?: number;
}

// Always asks for the lean `view=map` shape (just the fields the globe and
// list read) — the full row is fetched per event on demand.
export async function fetchCrises({ scope, days }: FetchCrisesOptions = {}): Promise<CrisisSummary[]> {
  const params = new URLSearchParams({ view: 'map' });
  if (scope) params.set('scope', scope);
  if (days !== undefined) params.set('days', String(days));
  const res = await fetch(`${API_BASE_URL}/api/crises?${params}`);
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
