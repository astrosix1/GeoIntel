import type {
  CrisesResponse,
  CrisisSummary,
  CrisisDetail,
  Briefing,
  CommentsPage,
  CountryProfile,
  EventComment,
  Me,
  Profile,
  ReportReason,
  SavedEvent,
  ScenariosResponse,
  StormsResponse,
  UserPrefs,
} from './types';
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

export type ScenariosErrorKind = 'sign_in_required' | 'premium_required' | 'unavailable' | 'error';

// Carries which failure it was so the UI can say the right thing (sign in /
// upgrade / "not available right now") instead of a generic error.
export class ScenariosError extends Error {
  kind: ScenariosErrorKind;
  constructor(kind: ScenariosErrorKind) {
    super(kind);
    this.kind = kind;
  }
}

// Premium: needs the user's token, and the server enforces it.
export async function fetchCrisisScenarios(id: string): Promise<ScenariosResponse> {
  const res = await authedFetch(`/api/crises/${encodeURIComponent(id)}/scenarios`);
  if (res.status === 401) throw new ScenariosError('sign_in_required');
  if (res.status === 403) throw new ScenariosError('premium_required');
  if (res.status === 503) throw new ScenariosError('unavailable');
  if (!res.ok) throw new ScenariosError('error');
  return res.json();
}

export type UserDataErrorKind =
  | 'sign_in_required'
  | 'premium_required'
  | 'unavailable'
  | 'limit_reached'
  | 'invalid'
  | 'error';

// Same idea as ScenariosError: which failure it was, so the UI says the right thing.
export class UserDataError extends Error {
  kind: UserDataErrorKind;
  constructor(kind: UserDataErrorKind) {
    super(kind);
    this.kind = kind;
  }
}

async function userDataRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedFetch(path, init);
  if (res.status === 401) throw new UserDataError('sign_in_required');
  if (res.status === 403) throw new UserDataError('premium_required');
  if (res.status === 503) throw new UserDataError('unavailable');
  if (res.status === 409) throw new UserDataError('limit_reached');
  if (res.status === 400) throw new UserDataError('invalid');
  if (!res.ok) throw new UserDataError('error');
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function fetchSaved(): Promise<SavedEvent[]> {
  return (await userDataRequest<{ saved: SavedEvent[] }>('/api/me/saved')).saved;
}

export async function saveEvent(crisisId: string): Promise<SavedEvent> {
  const body = await userDataRequest<{ saved: SavedEvent }>(`/api/me/saved/${encodeURIComponent(crisisId)}`, {
    method: 'PUT',
  });
  return body.saved;
}

export async function unsaveEvent(crisisId: string): Promise<void> {
  await userDataRequest<void>(`/api/me/saved/${encodeURIComponent(crisisId)}`, { method: 'DELETE' });
}

export function fetchPrefs(): Promise<UserPrefs> {
  return userDataRequest<UserPrefs>('/api/me/prefs');
}

export function savePrefs(hiddenOutlets: string[]): Promise<UserPrefs> {
  return userDataRequest<UserPrefs>('/api/me/prefs', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hidden_outlets: hiddenOutlets }),
  });
}

export type CommentsErrorKind =
  | 'sign_in_required'
  | 'premium_required'
  | 'profile_required'
  | 'name_taken'
  | 'slow_down'
  | 'invalid'
  | 'not_found'
  | 'unavailable'
  | 'error';

// Which failure it was, so the UI can say the right thing.
export class CommentsError extends Error {
  kind: CommentsErrorKind;
  constructor(kind: CommentsErrorKind) {
    super(kind);
    this.kind = kind;
  }
}

async function commentsRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedFetch(path, init);
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    if (body.error === 'profile_required') throw new CommentsError('profile_required');
    if (body.error === 'display_name_taken') throw new CommentsError('name_taken');
    throw new CommentsError('error');
  }
  if (res.status === 401) throw new CommentsError('sign_in_required');
  if (res.status === 403) throw new CommentsError('premium_required');
  if (res.status === 404) throw new CommentsError('not_found');
  if (res.status === 400) throw new CommentsError('invalid');
  if (res.status === 429) throw new CommentsError('slow_down');
  if (res.status === 503) throw new CommentsError('unavailable');
  if (!res.ok) throw new CommentsError('error');
  if (res.status === 204) return undefined as T;
  return res.json();
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// Sends the token when signed in so an author also sees their own hidden comments.
export function fetchComments(crisisId: string, before?: string): Promise<CommentsPage> {
  const query = before ? `?before=${encodeURIComponent(before)}` : '';
  return commentsRequest<CommentsPage>(`/api/crises/${encodeURIComponent(crisisId)}/comments${query}`);
}

export async function postComment(crisisId: string, body: string): Promise<EventComment> {
  const res = await commentsRequest<{ comment: EventComment }>(
    `/api/crises/${encodeURIComponent(crisisId)}/comments`,
    jsonInit('POST', { body }),
  );
  return res.comment;
}

export function deleteComment(commentId: string): Promise<void> {
  return commentsRequest<void>(`/api/comments/${encodeURIComponent(commentId)}`, { method: 'DELETE' });
}

export function reportComment(commentId: string, reason: ReportReason): Promise<{ reported: boolean; hidden: boolean }> {
  return commentsRequest(`/api/comments/${encodeURIComponent(commentId)}/report`, jsonInit('POST', { reason }));
}

export async function fetchProfile(): Promise<Profile | null> {
  return (await commentsRequest<{ profile: Profile | null }>('/api/me/profile')).profile;
}

export async function saveProfile(displayName: string): Promise<Profile> {
  const res = await commentsRequest<{ profile: Profile }>('/api/me/profile', jsonInit('PUT', { display_name: displayName }));
  return res.profile;
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
