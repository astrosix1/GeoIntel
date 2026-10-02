// Session handoff from the asix.live login. "Sign in" redirects to asix.live
// (VITE_ASIX_LOGIN_URL) with a return URL; asix.live sends the user back with
// the Supabase access token in the URL fragment (`#access_token=...`, the
// standard Supabase redirect shape). The token is picked up once at startup,
// stripped from the address bar, and kept in localStorage until it expires.
// The backend verifies it on every request — nothing here is trusted for
// access control, only for sending the token along.
//
// If asix.live ends up sharing a cookie across .asix.live instead, only
// readStoredToken()/captureTokenFromUrl() change; the rest of the app just
// calls getAccessToken().

const STORAGE_KEY = 'geointel.accessToken';

const LOGIN_URL: string | undefined = import.meta.env.VITE_ASIX_LOGIN_URL;
const UPGRADE_URL: string | undefined = import.meta.env.VITE_ASIX_UPGRADE_URL;

function tokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function isUsable(token: string): boolean {
  const exp = tokenExpiry(token);
  return exp !== null && exp > Date.now();
}

function readStoredToken(): string | null {
  try {
    const token = localStorage.getItem(STORAGE_KEY);
    if (token && isUsable(token)) return token;
    if (token) localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage can throw (private mode / blocked site data) — stay anonymous.
  }
  return null;
}

function captureTokenFromUrl(): void {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const token = params.get('access_token');
  if (!token) return;
  if (isUsable(token)) {
    try {
      localStorage.setItem(STORAGE_KEY, token);
    } catch {
      // Not persisted; this page load still works via the in-memory copy below.
      memoryToken = token;
    }
  }
  history.replaceState(null, '', window.location.pathname + window.location.search);
}

let memoryToken: string | null = null;
captureTokenFromUrl();

export function getAccessToken(): string | null {
  return readStoredToken() ?? (memoryToken && isUsable(memoryToken) ? memoryToken : null);
}

export function isSignInConfigured(): boolean {
  return !!LOGIN_URL;
}

export function getUpgradeUrl(): string | undefined {
  return UPGRADE_URL;
}

export function signIn(): void {
  if (!LOGIN_URL) return;
  const url = new URL(LOGIN_URL);
  url.searchParams.set('return_to', window.location.origin + window.location.pathname);
  window.location.assign(url.toString());
}

export function signOut(): void {
  memoryToken = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing to clear
  }
  window.location.reload();
}
