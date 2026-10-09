"""
Situations: different articles about one developing story, grouped. Stories (services/stories.py) merge repeats of
the same article or headline; a situation links the stories that tell the same event in different words, for
example five outlets' headlines on one set of criminal charges. Pure code, no model and no key:

  * headlines are compared by shared words weighted by how rare they are in the recent feed (a word in a few
    headlines says a lot, a word in hundreds says nothing),
  * two stories link only when they share at least two rare words, score above a threshold, are within a few days
    and at a compatible place,
  * a linked group is then checked for one theme (most of its members must share a core of words), so a popular
    name cannot chain unrelated stories together, and it is capped in size.

A situation is a grouping on top of stories: nothing is merged or deleted, and a situation reuses its earliest
story's id so anything keyed to that id (comments, saves, alerts) keeps working.
"""
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from cache import cache_clear_prefix
from models import Session, Crisis, Situation
from services.geo import distance_km
from services.stories import normalize_headline, significant_tokens, _country_names_by_iso, _UnionFind

logger = logging.getLogger(__name__)

WINDOW_DAYS = 3
MAX_GAP = timedelta(days=3)
RARE_DF = 40                # a word in more headlines than this is too common to link on
MIN_SHARED_RARE = 2
LINK_SCORE = 0.30           # IDF-weighted Jaccard of the two headlines
LINK_SCORE_3 = 0.20         # the lower bar when they share at least three rare words
FAR_KM = 800.0              # beyond this the places must be tagged alike, or the wording must be very close
STRONG_SHARED = 4           # this many shared rare words link whatever the place
MAX_SIZE = 60
CORE_SHARE = 0.5            # a word is "core" when at least this share of the members has it
MIN_STORIES = 2

_WIRE_TAIL = re.compile(r'(?<=\S)-(?:Xinhua|Reuters|AP|AFP|UPI|TASS|IANS|ANI|PTI|WAM|Anadolu)$')   # "...reported-Xinhua"
_OUTLET_TAIL = re.compile(r'\s[-–—]\s(?:(?!\s[-–—]\s).){2,90}$')


def headline_of(title):
    """The headline without its outlet decoration ("... | National News | site.com", "... - The Outlet")."""
    text = (title or '').split('|')[0].strip()
    if 'Ã' in text or 'â€' in text:        # UTF-8 read as Latin-1 ("NicolÃ¡s"): put it right when it round-trips
        try:
            text = text.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return _WIRE_TAIL.sub('', _OUTLET_TAIL.sub('', text)).strip().rstrip('-–— ')


def tokens_of(title):
    return significant_tokens(headline_of(title))


def countries_named(title):
    """The countries a headline itself names (names of four letters or more)."""
    by_iso, _ = _country_names_by_iso()
    head = f' {normalize_headline(headline_of(title))} '
    return frozenset(iso for iso, names in by_iso.items() if any(len(n) >= 4 and f' {n} ' in head for n in names))


class Item:
    """One story as grouping sees it."""
    __slots__ = ('id', 'title', 'tokens', 'named', 'country', 'tagged', 'lat', 'lon', 'date')

    def __init__(self, id, title, country, tagged, lat, lon, date):
        self.id = id
        self.title = title or ''
        self.tokens = tokens_of(title)
        self.named = countries_named(title)
        self.country = country
        self.tagged = frozenset(tagged or ())
        self.lat = lat
        self.lon = lon
        self.date = date

    @property
    def places(self):
        return self.tagged | ({self.country} if self.country else frozenset())


def _idf(items):
    df = Counter(t for it in items for t in it.tokens)
    n = max(1, len(items))
    return df, {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}


def _is_series(a, b):
    """Two headlines that differ only in their numbers or dates ("Arrests in X County: October 5" and "...: October 6") are a
    recurring feature, not one event."""
    plain = lambda t: re.sub(r'\d+', '', normalize_headline(headline_of(t)))
    return a.title != b.title and plain(a.title) == plain(b.title) and normalize_headline(a.title) != normalize_headline(b.title)


def _place_ok(a, b, shared_rare):
    if a.named and b.named and not (a.named & b.named):
        return False        # the headlines name different countries: "Peru Politics Explained" is not "Mexico Politics Explained"
    if shared_rare >= STRONG_SHARED or (a.places & b.places):
        return True
    if None in (a.lat, a.lon, b.lat, b.lon):
        return False
    return distance_km(a.lat, a.lon, b.lat, b.lon) <= FAR_KM


def _score(a, b, idf):
    union = a.tokens | b.tokens
    total = sum(idf[t] for t in union)
    return sum(idf[t] for t in a.tokens & b.tokens) / total if total else 0.0


def _one_theme(members):
    """Split a linked group whose members do not share a theme. Returns a list of groups (the group itself when it holds
    together, only the members that share a core word otherwise, the rest as singletons)."""
    if len(members) < 2:
        return [members]
    counts = Counter(t for it in members for t in it.tokens)
    need = max(2, math.ceil(CORE_SHARE * len(members)))
    core = {t for t, c in counts.items() if c >= need}
    if not core:
        return [[it] for it in members]
    keep = [it for it in members if it.tokens & core]
    rest = [[it] for it in members if not (it.tokens & core)]
    return [keep] + rest


def group_items(items):
    """Group `items` into situations. Returns a list of lists of Item (singletons included)."""
    n = len(items)
    df, idf = _idf(items)
    index = defaultdict(list)
    for i, it in enumerate(items):
        for t in it.tokens:
            if df[t] <= RARE_DF:
                index[t].append(i)
    shared = Counter()
    for members in index.values():
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                shared[(members[x], members[y])] += 1
    links = []
    for (i, j), count in shared.items():
        if count < MIN_SHARED_RARE:
            continue
        a, b = items[i], items[j]
        if abs(a.date - b.date) > MAX_GAP or not _place_ok(a, b, count) or _is_series(a, b):
            continue
        score = _score(a, b, idf)
        if score >= LINK_SCORE or (count >= 3 and score >= LINK_SCORE_3):
            links.append((score, i, j))
    links.sort(reverse=True)
    uf = _UnionFind(n)
    size = Counter()
    for _, i, j in links:
        ri, rj = uf.find(i), uf.find(j)
        if ri == rj:
            continue
        if size[ri] + 1 + size[rj] + 1 > MAX_SIZE:       # size[] counts members minus one
            continue
        uf.union(i, j)
        root = uf.find(i)
        size[root] = size[ri] + size[rj] + 1
    by_root = defaultdict(list)
    for i, it in enumerate(items):
        by_root[uf.find(i)].append(it)
    out = []
    for members in by_root.values():
        out.extend(_one_theme(members))
    return out


def lead_of(members):
    """The situation's lead story: the earliest (its id stays stable), ties to the id."""
    return min(members, key=lambda it: (it.date, it.id))


# --- storing ---------------------------------------------------------------------------

def build_recent(days=WINDOW_DAYS):
    """Group the last `days` of active, unmerged events into situations and store them. Idempotent. Returns a summary."""
    import json
    cutoff = datetime.utcnow() - timedelta(days=days)
    session = Session()
    summary = {'stories': 0, 'situations': 0, 'stories_grouped': 0}
    try:
        rows = (session.query(Crisis)
                .filter(Crisis.is_active.is_(True), Crisis.merged_into.is_(None), Crisis.date_start >= cutoff)
                .all())
        items = []
        for r in rows:
            if not r.title or not r.date_start:
                continue
            tagged = json.loads(r.also_tagged) if r.also_tagged else []
            items.append(Item(r.id, r.title, r.country, tagged, r.latitude, r.longitude, r.date_start))
        by_id = {r.id: r for r in rows}
        summary['stories'] = len(items)

        groups = [g for g in group_items(items) if len(g) >= MIN_STORIES]
        now = datetime.utcnow()
        member_ids = set()
        for members in groups:
            lead = lead_of(members)
            crises = [by_id[it.id] for it in members]
            situation = session.get(Situation, lead.id) or Situation(id=lead.id)
            main = max(crises, key=lambda c: (c.source_count or 1, -c.date_start.timestamp()))   # the most-reported headline names the pin
            situation.title = headline_of(main.title)[:200]
            situation.country = by_id[lead.id].country
            situation.story_count = len(members)
            situation.source_total = sum(c.source_count or 1 for c in crises)
            situation.first_at = min(it.date for it in members)
            situation.last_at = max(it.date for it in members)
            situation.updated_at = now
            session.merge(situation)
            for c in crises:
                c.situation_id = lead.id
                member_ids.add(c.id)
            summary['situations'] += 1
            summary['stories_grouped'] += len(members)
        # Stories no longer grouped (the group split or dissolved) are released.
        for r in rows:
            if r.situation_id and r.id not in member_ids:
                r.situation_id = None
        live_leads = {lead_of(g).id for g in groups}
        for s in session.query(Situation).all():
            if s.id not in live_leads and (s.last_at or now) >= cutoff:
                session.delete(s)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if summary['situations']:
        cache_clear_prefix('crises:')
        logger.info(f"Situations: {summary}")
    return summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Group related stories into situations (idempotent).')
    parser.add_argument('--days', type=int, default=WINDOW_DAYS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(build_recent(days=args.days))
