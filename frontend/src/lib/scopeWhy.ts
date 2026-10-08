// Why an event is in Global or Local, in plain words, from the reason the server stored (services/scope.py). This file
// imports nothing so it can be unit-tested (frontend/tests/scopewhy.test.ts).

export interface ScopeBasis {
  rule: string;
  global: string[];
  local: string[];
}

export interface ScopeWhy {
  summary: string;
  terms: string[];
}

const RULES: Record<string, string> = {
  'global terms': 'The headline matches international topics.',
  'local terms': 'The headline matches local news topics.',
  'local terms and a specific place': 'The headline has local words and the pin is precise to a town or city.',
  'actor noise': 'The feed lists a generic actor, or the same actor on both sides, which marks routine domestic news.',
  'tie: different states': 'The headline has both kinds of words and the two sides are different countries.',
  'tie: one state': 'The headline has both kinds of words and one country is on both sides.',
  'no match, default': 'No topic word matched, so it stays under Global.',
};

// null when the event has not been judged by topic yet (an older event, or a source that is not classified).
export function describeScope(scope: string | undefined, basis: ScopeBasis | null | undefined): ScopeWhy | null {
  if (!basis || typeof basis.rule !== 'string') return null;
  const summary = RULES[basis.rule];
  if (!summary) return null;
  const terms = scope === 'local' ? basis.local : basis.global;
  return { summary, terms: Array.isArray(terms) ? terms.filter((t) => typeof t === 'string') : [] };
}
