// The "outlet" of an event is the hostname of its source article, lowercased
// with a leading "www." stripped — the same normalisation the backend applies
// to a user's hidden-outlet list (services/user_data.normalise_outlets), so the
// two always agree. Events without a source URL have no outlet and are never
// hidden.
const HOST_RE = /^https?:\/\/([^/?#]+)/i;

export function outletOf(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = HOST_RE.exec(url);
  if (!match) return null;
  const host = match[1].toLowerCase().replace(/:\d+$/, '').replace(/^www\./, '');
  return host || null;
}
