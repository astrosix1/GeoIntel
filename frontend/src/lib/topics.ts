// Extra event categories that the news feed does not provide: Shootings, Protests, Elections and Crime. The feed only
// tags an event with a broad type (diplomatic, conflict, civil unrest, ...), so these are read from the headline. The
// rules are deliberately narrow (whole words, a few phrases) so a category is mostly right rather than full of noise,
// and an event can belong to more than one (a shooting at a protest is both). This file imports nothing so it can be
// unit-tested (frontend/tests/topics.test.ts).

export type Topic = 'shooting' | 'protest' | 'election' | 'crime';

export const TOPICS: { value: Topic; label: string }[] = [
  { value: 'shooting', label: 'Shootings' },
  { value: 'protest', label: 'Protests' },
  { value: 'election', label: 'Elections' },
  { value: 'crime', label: 'Crime' },
];

const SHOOTING = /\b(shoot(s|ing|ings|er|ers)?|shot (dead|and killed|and wounded|in the|at)|gunm[ae]n|gunfire|gunshots?|opened? fire|opens fire)\b/i;
// Aircraft, drones and missiles are "shot down", which is a military event, not a shooting.
const SHOT_DOWN = /\b(shoot(s|ing)? down|shot down|shoots? (at|down) (a|an|the)? ?(drone|plane|aircraft|jet|missile|helicopter))\b/i;
const PROTEST = /\b(protest(s|ers|ing|ed|or|ors)?|demonstrat(ion|ions|ors)|riot(s|ers|ing)?|unrest|rall(y|ies) (against|for|in|to)|march(es|ers)? (against|for|on))\b/i;
const ELECTION = /\b(elections?|electoral|ballots?|voters?|referendum|run-?off|polling stations?)\b/i;
const CRIME = /\b(murder(s|ed|er|ers)?|homicide|manslaughter|robber(y|ies)|burglar(y|ies)|theft|stab(s|bed|bing)?|kidnap(s|ped|ping)?|arrest(s|ed)?|fraud|smuggl(ing|er|ers)|trafficking|charged with|sentenced|police (say|said|investigat\w*))\b/i;

// The feed's own "civil_unrest" type is not used for Protests: checked against live data, about two thirds of those
// events are not protests at all (a train derailment, a prize announcement), so Protests goes by the headline alone and
// "Civil unrest" stays in the category list as the feed's own, looser type. The feed's "election" type is the same thing
// as the Elections topic, so it counts and is not listed twice.

export function topicsOf(event: { title?: string | null; type?: string | null }): Topic[] {
  const title = event.title ?? '';
  const topics: Topic[] = [];
  if (SHOOTING.test(title) && !SHOT_DOWN.test(title)) topics.push('shooting');
  if (PROTEST.test(title)) topics.push('protest');
  if (event.type === 'election' || ELECTION.test(title)) topics.push('election');
  if (CRIME.test(title)) topics.push('crime');
  return topics;
}

export function isTopic(value: string | null): value is Topic {
  return TOPICS.some((t) => t.value === value);
}

// The raw feed types that a topic replaces in the category list (they would only repeat it).
export const TYPES_COVERED_BY_TOPICS = new Set(['election']);

// "civil_unrest" -> "Civil unrest"
export function typeLabel(type: string): string {
  const spaced = type.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
