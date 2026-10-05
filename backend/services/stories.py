"""Merge duplicate and near-duplicate events into one story, keeping every source.

The feed often turns one article into several events and lets many outlets repeat
one wire story, so roughly a third of the events are repeats. Instead of dropping
the extras (which lost their sources), events about the same thing are merged:

  * one event stays as the story's primary (the earliest, so its id, and anything
    keyed to it, such as comments, saves and alerts, stays valid);
  * the others are kept but set inactive with `merged_into` pointing at the primary,
    so a merge can be reversed and old links still resolve;
  * every article becomes a `News` row on the primary, and `source_count` is the
    number of distinct outlets, so the story names all its sources.

Two tiers, cheapest first:
  1. Clear cases, pure code: the same article, the same headline, or headlines with
     very similar wording at the same place on nearly the same day.
  2. Borderline physical pairs: a small model answers yes/no on the two headlines.
     Each verdict is stored so a pair is judged once; a per-run cap bounds the cost.

Events are never merged across countries, across kinds (statement vs physical), or
when more than 2 days apart.
"""
import hashlib
import logging
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit

from cache import cache_clear_prefix
from data_sources.gdelt import GDELT_EVENT_VERB, GDELT_GENERIC_FALLBACK_TITLE_PREFIX
from models import Session, Crisis, News, StoryMergeCheck
from services.ai_client import AI_MERGE_MODEL, anthropic_client
from services.geo import distance_km

logger = logging.getLogger(__name__)

SIMILARITY_AUTO = 0.6          # headlines this alike, at the same place and time, are one story
SIMILARITY_BORDERLINE = 0.35   # below this they are different stories; between: ask the model
MIN_TOKENS = 3                 # a headline with fewer significant words says too little to match on
NEAR_KM = 11.0                 # "the same place": about 0.1 degree
SAME_DAY = timedelta(days=1)
MAX_GAP = timedelta(days=2)    # never merge events further apart than this
DEFAULT_WINDOW_DAYS = 3
DEFAULT_AI_PER_RUN = 40
ID_CHUNK = 400                 # keeps IN (...) lists under SQLite's variable limit
COMMIT_EVERY = 100

# Words that carry no identity: filler, and the "breaking/live" decorations headlines gain.
_STOP = frozenset("""
the and for with from that this these those into onto over under after before about amid
says said say has have had was were are will would could should been being his her their its
who whom whose what when where which while than then them they you your our out off but not
breaking live update updates watch video photos photo report reports news latest
""".split())
_TRACKING_PARAM = re.compile(r'^(utm_|fbclid$|gclid$|mc_|ref$|ref_|cmp$|ocid$|ito$|taid$|cid$)', re.I)


# --- normalisation and similarity -------------------------------------------------

def normalize_url(url):
    """A comparable form of an article URL: no scheme, no `www.`, no fragment, no
    trailing slash, tracking parameters dropped (other parameters kept: some sites
    identify the article by `?id=`). None for a blank or unusable URL."""
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = parts.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if not host:
        return None
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAM.match(k))
    path = parts.path.rstrip('/')
    return host + path + (('?' + urlencode(query)) if query else '')


def outlet_of(url):
    """The outlet behind a URL (its host without `www.`), or None."""
    if not url or not isinstance(url, str):
        return None
    try:
        host = urlsplit(url.strip()).netloc.lower()
    except ValueError:
        return None
    return (host[4:] if host.startswith('www.') else host) or None


def normalize_headline(title):
    """Lower-case, accents removed, punctuation gone, spaces collapsed."""
    if not title:
        return ''
    text = unicodedata.normalize('NFKD', title.lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


# The feed builds a stand-in title when it cannot read the article: "Conflict-related event in
# <country>", "<Actor> <verb phrase> <Actor or country>", or "<Actor> - conflict-related event in
# <country>". Two of those that match say nothing about what happened (two unrelated articles can
# both be "Police fights United States"), so they are never treated as a headline: such events merge
# only when they cite the very same article.
_VERB_PHRASES = sorted({t.split('{a2}')[0].strip() for t in GDELT_EVENT_VERB.values() if t.split('{a2}')[0].strip()},
                       key=len, reverse=True)
_GENERATED_SHAPE = re.compile(
    r'^\S+(?: \S+){0,3} (?:' + '|'.join(re.escape(v) for v in _VERB_PHRASES) + r')(?: \S+){1,4}$')


# Punctuation, quotes or digits: a real headline almost always has some; a stand-in never does.
_HEADLINE_MARKS = re.compile('[,:;.!?0-9"\'‘’“”|]')


def is_generated_title(title):
    """True for the feed's stand-in titles (see above), false for a real headline."""
    text = (title or '').strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith(GDELT_GENERIC_FALLBACK_TITLE_PREFIX.lower()) or 'conflict-related event in ' in lowered:
        return True
    # A real headline almost always has punctuation or a number; a stand-in never does.
    if _HEADLINE_MARKS.search(text):
        return False
    return bool(_GENERATED_SHAPE.match(text))


def significant_tokens(title):
    return frozenset(w for w in normalize_headline(title).split() if len(w) >= 3 and w not in _STOP)


def similarity(a, b):
    """Jaccard similarity of two token sets (0 when either is empty)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --- clustering ----------------------------------------------------------------------

class Ev:
    """The few fields of an event that merging looks at."""
    __slots__ = ('id', 'title', 'url', 'nurl', 'nhead', 'tokens', 'generated', 'country', 'scope', 'kind', 'lat',
                 'lon', 'date', 'confidence')

    def __init__(self, id, title, url, country, scope, kind, lat, lon, date, confidence):
        self.id = id
        self.title = title or ''
        self.url = url
        self.nurl = normalize_url(url)
        self.nhead = normalize_headline(title)
        self.generated = is_generated_title(title)
        # A stand-in title is not a headline: it takes no part in wording-based matching.
        self.tokens = frozenset() if self.generated else significant_tokens(title)
        self.country = country
        self.scope = scope
        self.kind = kind
        self.lat = lat
        self.lon = lon
        self.date = date
        self.confidence = confidence or 0


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _comparable(a, b):
    """The hard constraints: same country, scope and kind, and not too far apart in time."""
    return (a.country and a.country == b.country and a.scope == b.scope and a.kind == b.kind
            and abs(a.date - b.date) <= MAX_GAP)


def pick_primary(events):
    """The earliest event (so its id stays stable); ties go to the higher confidence, then the id."""
    return min(events, key=lambda e: (e.date, -e.confidence, e.id))


def cluster_events(events, judge=None):
    """Group `events` (a list of Ev) into stories. Returns (clusters, stats): clusters
    is a list of lists of Ev (singletons included); stats counts tier-1 and tier-2 merges.

    `judge(a, b)` is asked about borderline pairs (physical events, wording similar but
    not clearly the same) and returns True, False, or None for "can't say" (no model, or
    the budget is spent); None leaves the pair separate.
    """
    n = len(events)
    uf = _UnionFind(n)
    stats = {'tier1': 0, 'tier2_asked': 0, 'tier2_merged': 0}

    # Same article or same headline: a dictionary lookup, no pairwise comparison needed.
    for attr in ('nurl', 'nhead'):
        groups = defaultdict(list)
        for i, ev in enumerate(events):
            key = getattr(ev, attr)
            if key and (attr == 'nurl' or len(ev.tokens) >= MIN_TOKENS):   # short or stand-in headlines are not identity
                groups[(ev.country, ev.scope, ev.kind, key)].append(i)
        for members in groups.values():
            members.sort(key=lambda i: events[i].date)
            for a, b in zip(members, members[1:]):
                if _comparable(events[a], events[b]):
                    uf.union(a, b)

    # Similar wording at the same place: only compare events in neighbouring map cells.
    cells = defaultdict(list)
    for i, ev in enumerate(events):
        if ev.country and len(ev.tokens) >= MIN_TOKENS:
            cells[(ev.country, ev.scope, ev.kind, round(ev.lat / 0.1), round(ev.lon / 0.1))].append(i)

    borderline = []
    for i, a in enumerate(events):
        if not (a.country and len(a.tokens) >= MIN_TOKENS):
            continue
        cx, cy = round(a.lat / 0.1), round(a.lon / 0.1)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((a.country, a.scope, a.kind, cx + dx, cy + dy), ()):
                    if j <= i:
                        continue
                    b = events[j]
                    if not _comparable(a, b) or distance_km(a.lat, a.lon, b.lat, b.lon) > NEAR_KM:
                        continue
                    score = similarity(a.tokens, b.tokens)
                    if score >= SIMILARITY_AUTO and abs(a.date - b.date) <= SAME_DAY:
                        uf.union(i, j)
                    elif SIMILARITY_BORDERLINE <= score < SIMILARITY_AUTO and a.kind == 'physical':
                        borderline.append((i, j))

    stats['tier1'] = n - len({uf.find(i) for i in range(n)})

    # Borderline pairs, one question per pair of stories.
    if judge and borderline:
        asked = set()
        for i, j in borderline:
            ri, rj = uf.find(i), uf.find(j)
            pair = (min(ri, rj), max(ri, rj))
            if ri == rj or pair in asked:
                continue
            verdict = judge(events[i], events[j])
            if verdict is None:
                continue
            asked.add(pair)
            stats['tier2_asked'] += 1
            if verdict:
                uf.union(i, j)
                stats['tier2_merged'] += 1

    by_root = defaultdict(list)
    for i, ev in enumerate(events):
        by_root[uf.find(i)].append(ev)
    return list(by_root.values()), stats


# --- the model's say on borderline pairs ----------------------------------------------

_JUDGE_TOOL = {
    'name': 'same_event',
    'description': 'Record whether the two headlines report the same specific event.',
    'input_schema': {
        'type': 'object',
        'properties': {'same_event': {'type': 'boolean'}},
        'required': ['same_event'],
    },
}


def _model_available():
    return bool(anthropic_client and getattr(anthropic_client, 'api_key', None))


def _ask_model(a, b):
    message = anthropic_client.messages.create(
        model=AI_MERGE_MODEL,
        max_tokens=60,
        tools=[_JUDGE_TOOL],
        tool_choice={'type': 'tool', 'name': 'same_event'},
        messages=[{'role': 'user', 'content': (
            'Do these two news headlines report the SAME specific event: the same incident, '
            'involving the same people or places, at about the same time? Two separate incidents '
            'of the same kind (two different shootings, two different protests) are NOT the same '
            'event. When unsure, answer false.\n\n'
            f'A: {a.title[:200]}\nB: {b.title[:200]}')}],
    )
    for block in message.content:
        if getattr(block, 'type', None) == 'tool_use':
            value = (block.input or {}).get('same_event')
            return value if isinstance(value, bool) else None
    return None


def _make_judge(session, budget):
    """A judge(a, b) that checks the stored verdicts first, then asks the model while the
    budget lasts. Verdicts are written as they are made; a model failure is not stored."""
    state = {'left': budget}

    def judge(a, b):
        key = '|'.join(sorted((a.id, b.id)))
        stored = session.query(StoryMergeCheck).filter(StoryMergeCheck.pair_key == key).first()
        if stored is not None:
            return stored.same_event
        if state['left'] <= 0 or not _model_available():
            return None
        state['left'] -= 1
        try:
            verdict = _ask_model(a, b)
        except Exception as e:
            logger.warning(f"Merge check failed: {e}")
            return None
        if verdict is None:
            return None
        session.add(StoryMergeCheck(pair_key=key, same_event=verdict, checked_at=datetime.utcnow()))
        session.flush()
        return verdict

    return judge


def ai_budget():
    try:
        return max(0, int(os.getenv('STORY_MERGE_AI_PER_RUN', DEFAULT_AI_PER_RUN)))
    except ValueError:
        return DEFAULT_AI_PER_RUN


# --- writing merged stories -------------------------------------------------------------

def _news_id(primary_id, nurl):
    return f"{primary_id}:{hashlib.sha1(nurl.encode('utf-8')).hexdigest()[:16]}"


def _chunks(items, size=ID_CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _merge_cluster(session, members, now):
    """Fold one cluster of events into its primary. Returns the number of events merged away."""
    primary_ev = pick_primary(members)
    ids = [e.id for e in members]
    rows = {}
    news_rows = []
    for chunk in _chunks(ids):
        rows.update({c.id: c for c in session.query(Crisis).filter(Crisis.id.in_(chunk)).all()})
        news_rows.extend(session.query(News).filter(News.crisis_id.in_(chunk)).all())
    primary = rows[primary_ev.id]
    dupe_ids = {i for i in ids if i != primary.id}

    # Every article the story rests on: each member's own, plus any already attached to a
    # member (a story merged earlier into a member keeps its sources).
    sources = {}
    for ev in members:
        nurl = ev.nurl
        if nurl and nurl not in sources:
            sources[nurl] = (ev.url, ev.title, ev.date)
    for n in news_rows:
        nurl = normalize_url(n.url)
        if nurl and nurl not in sources:
            sources[nurl] = (n.url, n.title, n.published_at)
    for n in news_rows:
        if n.crisis_id in dupe_ids:
            session.delete(n)           # re-created under the primary below

    outlets = set()
    for nurl, (url, title, published) in sources.items():
        outlet = outlet_of(url) or 'unknown'
        outlets.add(outlet)
        session.merge(News(id=_news_id(primary.id, nurl), crisis_id=primary.id, title=(title or '')[:300],
                           url=url[:500], source=outlet[:100], published_at=published, fetched_at=now))

    primary.source_count = max(1, len(outlets))
    from services.severity import rescore
    rescore(primary)    # corroboration changed
    primary.confidence = max(primary.confidence or 50, min(95, 50 + 5 * primary.source_count))
    for dupe_id in dupe_ids:
        dupe = rows[dupe_id]
        dupe.merged_into = primary.id
        dupe.is_active = False
    return len(dupe_ids)


def merge_recent(days=DEFAULT_WINDOW_DAYS, ai_per_run=None):
    """Merge the last `days` of active GDELT events into stories. Idempotent: events already
    merged are not touched again, and a late article joins the existing story. Returns a
    summary dict."""
    budget = ai_budget() if ai_per_run is None else ai_per_run
    summary = {'events': 0, 'stories_merged': 0, 'events_merged': 0, 'tier1': 0, 'tier2_asked': 0,
               'tier2_merged': 0}
    cutoff = datetime.utcnow() - timedelta(days=days)
    session = Session()
    try:
        rows = (session.query(Crisis.id, Crisis.title, Crisis.source_url, Crisis.country, Crisis.scope,
                              Crisis.event_kind, Crisis.latitude, Crisis.longitude, Crisis.date_start,
                              Crisis.confidence)
                .filter(Crisis.source == 'GDELT', Crisis.is_active.is_(True), Crisis.merged_into.is_(None),
                        Crisis.date_start >= cutoff)
                .all())
        events = [Ev(r.id, r.title, r.source_url, r.country, r.scope, r.event_kind, r.latitude, r.longitude,
                     r.date_start or datetime.utcnow(), r.confidence) for r in rows]
        summary['events'] = len(events)

        clusters, stats = cluster_events(events, judge=_make_judge(session, budget))
        summary.update({k: stats[k] for k in ('tier1', 'tier2_asked', 'tier2_merged')})

        now = datetime.utcnow()
        done = 0
        for members in clusters:
            if len(members) < 2:
                continue
            summary['events_merged'] += _merge_cluster(session, members, now)
            summary['stories_merged'] += 1
            done += 1
            if done % COMMIT_EVERY == 0:
                session.commit()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if summary['events_merged']:
        cache_clear_prefix('crises:')
        logger.info(f"Story merge: {summary}")
    return summary


def canonical_id(crisis_id):
    """The story a crisis id belongs to: its primary if it was merged away, else itself."""
    session = Session()
    try:
        row = session.query(Crisis.merged_into).filter(Crisis.id == crisis_id).first()
        return row.merged_into if row and row.merged_into else crisis_id
    finally:
        session.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Merge duplicate events into stories (idempotent).')
    parser.add_argument('--days', type=int, default=7, help='how many days back to merge (default 7)')
    parser.add_argument('--no-ai', action='store_true', help='skip the borderline-pair model check')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(merge_recent(days=args.days, ai_per_run=0 if args.no_ai else None))
