"""
Duplicates: one real-world event -> one Crisis row.

The same event reached the globe many times over:
  - GDELT codes several events per article (one live file: 186 events from
    60 URLs), so one story became a cluster of pins.
  - The same story from different outlets, queries and languages each became
    its own row. Crisis rows were only ever matched by id.

Two steps:
  - cluster_batch(): within one connector's batch, group reports of the
    same event (same canonical URL, or same country + type family + time
    window + similar title/place — see is_match) and pick a primary.
  - find_existing(): at upsert time, match a primary against ACTIVE rows
    already in the database (same id, a crisis_sources URL, or is_match), so
    a report arriving in a later sync, or from a later connector in the same
    sync, merges into the existing event instead of adding a pin.

Merging (DataAggregator._store_cluster) keeps the primary's id, so severity
snapshots and forecasts stay attached, adds a crisis_sources row per report
and sets source_count.
"""
import math
import re
from datetime import timedelta
from functools import lru_cache

from .config import get_config
from .normalize import canonical_url

_PRECISION_RANK = {'point': 4, 'city': 3, 'region': 2, 'country': 1}
_WORD_RE = re.compile(r"[a-z0-9]+")


def _cfg():
    return get_config().get('dedup', {})


# ── views: the fields matching needs, from a candidate or a DB row ─────────

def view_from_candidate(candidate, meta):
    return {
        'id': candidate.get('id'),
        'country_code': meta.get('country_code'),
        'type': candidate.get('type'),
        'date': candidate.get('date_start'),
        'lat': candidate.get('latitude'),
        'lon': candidate.get('longitude'),
        'precision': meta.get('location_precision') or 'city',
        'tokens': title_tokens(candidate.get('title')),
        'url': canonical_url(meta.get('url')) if meta.get('url') else None,
        'synthesized': bool(meta.get('title_synthesized')),
    }


def view_from_row(row):
    return {
        'id': row.id,
        'country_code': row.country_code,
        'type': row.type,
        'date': row.date_start,
        'lat': row.latitude,
        'lon': row.longitude,
        'precision': row.location_precision or 'city',
        'tokens': title_tokens(row.title),
        'url': canonical_url(row.source_url) if row.source_url else None,
        'synthesized': False,
    }


# ── similarity ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _entity_words():
    """Words that name a place or a country — they weigh double, since two
    headlines about the same event almost always share them."""
    from .location import load_gazetteer
    words = set()
    for city in load_gazetteer():
        words.update(_WORD_RE.findall(city))
    from .countries import _load
    for record in _load()[0].values():
        for name in [record['name'], *record.get('aliases', []), *record.get('demonyms', [])]:
            words.update(w for w in _WORD_RE.findall(name.lower()) if len(w) > 2)
    return frozenset(words)


def _stem(word):
    for suffix in ('ing', 'ed', 'es', 's'):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def title_tokens(title):
    """Title words -> weight (places/countries 2, everything else 1)."""
    if not title:
        return {}
    stop = set(_cfg().get('stopwords', []))
    entities = _entity_words()
    tokens = {}
    for word in _WORD_RE.findall(title.lower()):
        if word in stop:
            continue
        tokens[_stem(word)] = 2 if word in entities else 1
    return tokens


def similarity(a, b):
    """Weighted Jaccard of two title_tokens() maps."""
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    shared = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys if k in a and k in b)
    total = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return shared / total if total else 0.0


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


@lru_cache(maxsize=1)
def _families():
    out = {}
    for family, types in _cfg().get('type_families', {}).items():
        for t in types:
            out[t] = family
    return out


def type_family(crisis_type):
    return _families().get(crisis_type, 'other')


def is_match(a, b):
    """Are two event views reports of the same real-world event?"""
    if a['url'] and a['url'] == b['url']:
        return True
    cfg = _cfg()
    if not a['country_code'] or a['country_code'] != b['country_code']:
        return False
    if type_family(a['type']) != type_family(b['type']):
        return False
    if a['date'] and b['date'] and abs(a['date'] - b['date']) > timedelta(hours=cfg.get('window_hours', 48)):
        return False

    sim = similarity(a['tokens'], b['tokens'])
    if sim >= cfg.get('any_similarity', 0.6):
        return True
    if None in (a['lat'], a['lon'], b['lat'], b['lon']):
        return False
    distance = haversine_km(a['lat'], a['lon'], b['lat'], b['lon'])
    precise = (_PRECISION_RANK.get(a['precision'], 0) >= 3 and _PRECISION_RANK.get(b['precision'], 0) >= 3)
    if precise and distance <= cfg.get('city_distance_km', 50) and sim >= cfg.get('city_similarity', 0.35):
        return True
    if (a['synthesized'] or b['synthesized']) and precise \
            and distance <= cfg.get('same_place_km', 10) \
            and sim >= cfg.get('same_place_synthesized_similarity', 0.2):
        return True
    return False


# ── primary selection ──────────────────────────────────────────────────────

_SOURCE_PRIORITY = {'ACLED': 4, 'CURATED': 5, 'MANUAL': 5, 'GDELT': 1}
_CODE_TIER = {'20': 6, '19': 5, '18': 4, '17': 3, '15': 2, '16': 2, '13': 1}


def source_priority(source, outlet=None):
    """ACLED (curated conflict data) > reliable outlets > other news > GDELT."""
    if source in _SOURCE_PRIORITY:
        return _SOURCE_PRIORITY[source]
    if source and (source.startswith('NEWS_API') or source == 'NewsAPI'):
        from .relevance import _reliability_scores
        score = _reliability_scores().get((outlet or '').lower(), 0)
        return 3 if score >= 85 else 2
    return 2


def _rank(item):
    candidate, meta = item
    g = meta.get('gdelt') or {}
    code = str(g.get('base_code') or g.get('event_code') or '')[:2]
    return (
        source_priority(candidate.get('source'), meta.get('outlet')),
        _PRECISION_RANK.get(meta.get('location_precision'), 0),
        _CODE_TIER.get(code, 0),
        int(g.get('num_articles') or 0),
        not meta.get('title_synthesized'),
        len(candidate.get('title') or ''),
    )


def cluster_batch(items):
    """Group (candidate, meta) items that report the same event. Returns a
    list of clusters, each a list of items with the primary first."""
    position = {id(item): i for i, item in enumerate(items)}
    ordered = sorted(items, key=_rank, reverse=True)   # best report of each event becomes its primary
    clusters = []     # [ {'view': primary view, 'items': [...], 'urls': set()} ]
    for item in ordered:
        view = view_from_candidate(*item)
        home = None
        for cluster in clusters:
            if (view['url'] and view['url'] in cluster['urls']) or is_match(cluster['view'], view):
                home = cluster
                break
        if home is None:
            clusters.append({'view': view, 'items': [item], 'urls': {view['url']} - {None}})
        else:
            home['items'].append(item)
            if view['url']:
                home['urls'].add(view['url'])
    # Output in input order (by each event's first report).
    clusters.sort(key=lambda c: min(position[id(item)] for item in c['items']))
    return [c['items'] for c in clusters]


# ── provenance ─────────────────────────────────────────────────────────────

def source_record(candidate, meta):
    """A crisis_sources row (as a dict) for one report."""
    url = meta.get('url')
    key = canonical_url(url) if url else f"{candidate.get('source')}:{candidate.get('source_id') or candidate.get('id')}"
    return {
        'source': candidate.get('source'),
        'external_id': str(candidate.get('source_id') or candidate.get('id') or '')[:100] or None,
        'url_key': key[:500],
        'url': url,
        'outlet': (meta.get('outlet') or '')[:100] or None,
        'title': (candidate.get('title') or '')[:300] or None,
        'published_at': candidate.get('date_start'),
    }


# ── matching against the database ──────────────────────────────────────────

def find_existing(session, candidate, meta, sources):
    """An active Crisis row this primary should merge into, or None."""
    from models import Crisis, CrisisSource

    keys = [s['url_key'] for s in sources]
    if keys:
        hit = (session.query(Crisis)
               .join(CrisisSource, CrisisSource.crisis_id == Crisis.id)
               .filter(CrisisSource.url_key.in_(keys), Crisis.is_active == True)  # noqa: E712
               .first())
        if hit:
            return hit

    view = view_from_candidate(candidate, meta)
    if not view['country_code'] or not view['date']:
        return None
    lookback = timedelta(hours=_cfg().get('db_lookback_hours', 72))
    rows = (session.query(Crisis)
            .filter(Crisis.is_active == True,  # noqa: E712
                    Crisis.country_code == view['country_code'],
                    Crisis.date_start >= view['date'] - lookback,
                    Crisis.date_start <= view['date'] + lookback)
            .limit(500).all())
    for row in rows:
        if row.id != candidate['id'] and is_match(view_from_row(row), view):
            return row
    return None
