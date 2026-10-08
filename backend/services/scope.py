"""
Global or Local: which of the two news views an event belongs to, decided from what the event is about.

The terms live in data_sources/scope_terms.json (the owner's two lists, as weighted groups). This module is pure: it takes
text and a few facts about the event and returns the scope and the terms that decided it, so every event can say why.

Rules (docs/global-local-filter-plan.md):
  1. Terms match as whole words or phrases. Acronyms (UN, EU, WHO) match only when written exactly so.
  2. Each distinct term found adds its group's weight to its side. Weight 3 is strong alone, 2 is medium, 1 is weak
     (all weak terms together count as 1).
  3. Global when global >= 3, or global >= 2 and it beats local. (A named institution settles it: "Mayor attends UN summit".)
  4. Local when local >= 2 and beats global, or any local term with no global term at all and a specific place (unless two different states are the actors), or the
     existing actor-noise signal (unless rule 3 applies).
  5. Both sides present but neither clear: two different states as actors means global, one state on both sides means local.
  6. Neither list matches: the event keeps the side the older rules gave it (`noise` true means local, else global).
"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

TERMS_PATH = Path(__file__).resolve().parent.parent / 'data_sources' / 'scope_terms.json'
STRONG = 3
MEDIUM = 2


@lru_cache(maxsize=1)
def _compiled():
    data = json.loads(TERMS_PATH.read_text(encoding='utf-8'))
    groups = []
    for group in data['groups']:
        flags = 0 if group.get('case') == 'sensitive' else re.IGNORECASE
        # Longest first so "city council meeting" is reported rather than "city council"; "s?" lets plurals match.
        terms = sorted({t.strip() for t in group['terms'] if t.strip()}, key=len, reverse=True)
        pattern = re.compile(r'(?<![\w])(' + '|'.join(re.escape(t) for t in terms) + r')(?:s|es)?(?![\w])', flags)
        groups.append({'name': group['name'], 'side': group['side'], 'weight': group['weight'], 'pattern': pattern, 'ignore': flags != 0})
    return groups


def find_terms(text):
    """[(term, group name, side, weight)] for every distinct term found in the text (a term counts once)."""
    found, seen = [], set()
    for group in _compiled():
        for match in group['pattern'].finditer(text or ''):
            term = match.group(1)
            key = (group['side'], term.lower() if group['ignore'] else term)
            if key in seen:
                continue
            seen.add(key)
            found.append((term, group['name'], group['side'], group['weight']))
    return found


def _score(terms):
    """Medium and strong terms add up; weak terms (weight 1) together add at most 1, because words like "war", "police" and
    "school" turn up in both kinds of story and several of them in one headline are not more convincing than one."""
    return sum(w for _, w in terms if w > 1) + (1 if any(w == 1 for _, w in terms) else 0)


def classify(text, *, place_specific=False, actors_differ=None, noise=False):
    """
    text: the headline plus any short extra text (a fact summary).
    place_specific: the event is pinned to a named town or suburb rather than a country.
    actors_differ: True if the two actors are different states, False if the same one, None if unknown.
    noise: the older actor-noise signal fired (generic actor, self-referential pair, blank actor under violence).
    Returns {'scope': 'global'|'local', 'rule': str, 'global': [terms], 'local': [terms], 'global_score': n, 'local_score': n}.
    """
    found = find_terms(text)
    g_terms = [(t, w) for t, _, side, w in found if side == 'global']
    l_terms = [(t, w) for t, _, side, w in found if side == 'local']
    g = _score(g_terms)
    l = _score(l_terms)

    def result(scope, rule):
        return {'scope': scope, 'rule': rule, 'global': [t for t, _ in g_terms], 'local': [t for t, _ in l_terms],
                'global_score': g, 'local_score': l}

    if g >= STRONG or (g >= MEDIUM and g > l):
        return result('global', 'global terms')
    if noise:
        return result('local', 'actor noise')
    if l >= MEDIUM and l > g:
        return result('local', 'local terms')
    if l >= 1 and g == 0 and place_specific and actors_differ is not True:
        return result('local', 'local terms and a specific place')
    if g and l:
        if actors_differ is True:
            return result('global', 'tie: different states')
        if actors_differ is False:
            return result('local', 'tie: one state')
    return result('global', 'no match, default')


MAX_BASIS_TERMS = 6


def basis_json(verdict):
    """The stored reason: the rule and the first few terms that decided it, small enough to keep on every row."""
    return json.dumps({'rule': verdict['rule'], 'global': verdict['global'][:MAX_BASIS_TERMS], 'local': verdict['local'][:MAX_BASIS_TERMS]},
                      ensure_ascii=False, separators=(',', ':'))


def _summary(facts):
    try:
        return ((json.loads(facts) or {}).get('summary') or '') if facts else ''
    except (ValueError, TypeError):
        return ''


def judge_missing(batch=500):
    """Judge every event that has no scope_basis yet (events from before this feature) and store the verdict. The event's
    present scope came from the old actor-noise rule, so Local counts as that signal. Safe to run any time: it only touches
    events with no basis, so a second run does nothing. Returns (judged, moved)."""
    from models import Session, Crisis
    log = logging.getLogger(__name__)
    judged = moved = 0
    session = Session()
    try:
        while True:
            rows = session.query(Crisis).filter(Crisis.scope_basis.is_(None)).limit(batch).all()
            if not rows:
                break
            for row in rows:
                verdict = classify(f'{row.title} {_summary(row.facts)}', place_specific=(row.location_confidence or 0) >= 85,
                                   noise=(row.scope == 'local'))
                if row.scope != verdict['scope']:
                    row.scope = verdict['scope']
                    moved += 1
                row.scope_basis = basis_json(verdict)
                judged += 1
            session.commit()
        log.info('Judged Global/Local for %s events (%s changed side)', judged, moved)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return judged, moved


if __name__ == '__main__':
    print('judged %s events, %s changed side' % judge_missing())
