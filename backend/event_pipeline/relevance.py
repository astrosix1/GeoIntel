"""
Geopolitical relevance: is this candidate actually a geopolitical event, and
does it come from somewhere that publishes news rather than sport, gossip or
press releases?

What was getting through:
  - GDELT had no actor, root-event or corroboration rules, so a Formula 1
    article became a "conflict in Baku", a 1934 cruise-ship history piece a
    FIGHT at severity 100, and celebrity gossip, a whale carcass and a
    football verdict all showed up as crises.
  - NewsAPI only needed a crisis keyword plus a known city.
  - ACLED's peaceful protests and administrative "strategic developments"
    showed up alongside real violence.

Each check returns None (keep) or a reason code. Candidates without the
relevant `_meta` (sample and curated rows) pass untouched. All thresholds
and word lists are in config/event_filters.json.
"""
import json
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit, unquote

from .config import get_config
from .keywords import has_keyword, strip_excluded_phrases

_RELIABILITY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'source_reliability.json'
)

# "in 1934", "in 2011" — a year well in the past signals history/retrospective
# content, not a current event.
_PAST_YEAR_RE = re.compile(r'\bin\s+(?:1[0-9]\d\d|200\d|201\d)\b')


# ── outlets ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _reliability_scores():
    try:
        with open(_RELIABILITY_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k.lower(): v for k, v in raw.items() if not k.startswith('_')}


def _host(url):
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def check_outlet(url=None, outlet=None):
    """Reject press-release wires, sport/entertainment/finance outlets and
    non-news sections of general outlets. Returns a reason code or None."""
    cfg = get_config().get('outlets', {})
    host = _host(url) if url else ''
    if host:
        for domain in cfg.get('blocked_domains', []):
            if host == domain or host.endswith('.' + domain):
                return 'blocked_outlet'
    if outlet and outlet.strip().lower() in {n.lower() for n in cfg.get('blocked_outlet_names', [])}:
        return 'blocked_outlet'

    if url:
        try:
            path = unquote(urlsplit(url).path).lower()
        except ValueError:
            path = ''
        sections = cfg.get('blocked_sections', [])
        # Skip the last segment — that's the article slug, where a word like
        # "football" is content (handled by topic checks), not a section.
        for segment in [s for s in path.split('/') if s][:-1]:
            if any(segment == s or segment.startswith(s + '-') for s in sections):
                return 'blocked_section'

    min_reliability = cfg.get('min_reliability', 0)
    if min_reliability:
        scores = _reliability_scores()
        score = scores.get((outlet or '').lower(), scores.get(host, cfg.get('default_reliability', 65)))
        if score < min_reliability:
            return 'low_reliability_outlet'
    return None


# ── topic signals ──────────────────────────────────────────────────────────

def _news_cfg():
    return get_config().get('news_relevance', {})


def is_off_topic(text):
    """Sport, entertainment, markets, accidents, history pieces..."""
    if not text:
        return False
    text = strip_excluded_phrases(text.lower())
    return has_keyword(text, _news_cfg().get('negative_topics', [])) or bool(_PAST_YEAR_RE.search(text))


@lru_cache(maxsize=1)
def _gazetteer_countries():
    # Country names from the curated city table — a real country mention is
    # an actor signal. (Replaced by config/countries.json in phase 4.)
    from data_sources import NewsBasedCrisisDetector
    return tuple(sorted({v['country'].lower() for v in NewsBasedCrisisDetector.LOCATION_MAP.values()}))


def has_actor_signal(text, stakeholders=()):
    if stakeholders:
        return True
    cfg = _news_cfg()
    text = text.lower()
    return (has_keyword(text, cfg.get('role_terms', []))
            or has_keyword(text, cfg.get('military_action_terms', []))
            or has_keyword(text, cfg.get('demonyms', []))
            or has_keyword(text, list(_gazetteer_countries())))


def _stakeholder_list(candidate):
    raw = candidate.get('stakeholders') or ''
    return [s for s in (raw.split(',') if isinstance(raw, str) else raw) if s]


# ── per-source checks ──────────────────────────────────────────────────────

def check_news(candidate, meta):
    """NewsAPI (and multilingual): the connector already required a crisis
    keyword (the action signal); here we require an actor signal too and
    reject off-topic stories unless several states are named."""
    reason = check_outlet(meta.get('url'), meta.get('outlet'))
    if reason:
        return reason
    text = meta.get('text') or candidate.get('title') or ''
    stakeholders = _stakeholder_list(candidate)
    strong = len(set(stakeholders)) >= _news_cfg().get('strong_actor_min', 2)
    if is_off_topic(text) and not strong:
        return 'off_topic'
    if not has_actor_signal(text, stakeholders):
        return 'no_geopolitical_actor'
    return None


def _gdelt_actor(g, n):
    code = (g.get(f'actor{n}_code') or '').strip()
    if not code:
        return None
    country = (g.get(f'actor{n}_country') or '').strip()
    kind = (g.get(f'actor{n}_type') or '').strip()
    return {'code': code, 'country': country, 'type': kind}


def _is_geopolitical_actor(actor, cfg):
    if actor is None:
        return False
    if actor['type'] in cfg.get('geopolitical_actor_types', []):
        return True
    # No type but the actor IS a country (code "RUS", country "RUS"): the state itself.
    return not actor['type'] and bool(actor['country']) and actor['code'] == actor['country']


def check_gdelt(candidate, meta):
    """GDELT strict keep rules (see gdelt_rules in config and
    docs/EVENT_FILTERING.md §2)."""
    cfg = get_config().get('gdelt_rules', {})
    g = meta.get('gdelt') or {}

    reason = check_outlet(meta.get('url'))
    if reason:
        return reason
    if cfg.get('require_root_event', True) and str(g.get('is_root_event', '1')) != '1':
        return 'not_root_event'

    actors = [a for a in (_gdelt_actor(g, 1), _gdelt_actor(g, 2)) if a]
    if not actors:
        return 'no_actors'
    geo_actors = [a for a in actors if _is_geopolitical_actor(a, cfg)]
    if not geo_actors:
        return 'non_geopolitical_actors'
    interstate = (
        len(geo_actors) == 2
        and geo_actors[0]['country'] and geo_actors[1]['country']
        and geo_actors[0]['country'] != geo_actors[1]['country']
    )

    code = str(g.get('base_code') or g.get('event_code') or '')[:3]

    if not interstate:
        # Domestic event: needs an explicitly typed actor fitting the event
        # family — armed groups for assaults and fighting, political targets
        # for arrests and repression. A bare country code doesn't count here.
        required = cfg.get('domestic_actor_types', {})
        allowed = required.get(code[:2], required.get('default', cfg.get('geopolitical_actor_types', [])))
        if not any(a['type'] in allowed for a in actors):
            return 'domestic_non_political'

    num_sources = int(g.get('num_sources') or 0)
    num_articles = int(g.get('num_articles') or 0)
    actor_types = {a['type'] for a in actors}

    if code in cfg.get('dropped_codes', []):
        return 'vague_event_code'
    protest = cfg.get('protest', {})
    if code.startswith(protest.get('prefix', '14')):
        if num_articles < protest.get('min_articles', 5) and not (actor_types & set(protest.get('actor_types', []))):
            return 'minor_protest'
    elif any(code.startswith(p) for p in cfg.get('interstate_only_prefixes', [])):
        if not interstate:
            return 'domestic_verbal_conflict'
    elif not any(code.startswith(p) for p in cfg.get('standalone_prefixes', [])):
        return 'event_code_not_eligible'

    if cfg.get('check_headline_topics', True):
        headline = ' '.join(filter(None, [meta.get('headline'), _url_words(meta.get('url'))]))
        if is_off_topic(headline) and not interstate:
            return 'off_topic'

    corroboration = cfg.get('corroboration', {})
    exempt = (
        any(code.startswith(p) for p in corroboration.get('exempt_prefixes', []))
        and actor_types & set(cfg.get('armed_actor_types', []))
    )
    if not exempt and num_sources < corroboration.get('min_sources', 2) \
            and num_articles < corroboration.get('min_articles', 3):
        return 'uncorroborated'
    return None


def _url_words(url):
    if not url:
        return ''
    try:
        path = unquote(urlsplit(url).path)
    except ValueError:
        return ''
    return re.sub(r'[-_/+.]+', ' ', path)


def check_acled(candidate, meta):
    cfg = get_config().get('acled_rules', {})
    a = meta.get('acled') or {}
    try:
        fatalities = int(a.get('fatalities') or 0)
    except (TypeError, ValueError):
        fatalities = 0
    if fatalities > 0:
        return None
    sub_type = (a.get('sub_event_type') or '').strip()
    if sub_type in cfg.get('drop_without_fatalities', []):
        return 'low_signal_acled_event'
    if (a.get('event_type') or '').strip() == 'Strategic developments':
        actors = ' '.join(filter(None, [a.get('actor1'), a.get('actor2')]))
        state_actor = any(m in actors for m in cfg.get('state_actor_markers', []))
        if sub_type not in cfg.get('strategic_developments_keep', []) or not state_actor:
            return 'low_signal_acled_event'
    return None


_CHECKS = {'news': check_news, 'gdelt': check_gdelt, 'acled': check_acled}


def check_relevance(candidate, meta):
    """Dispatch on meta['kind']; candidates without one (sample/curated) pass."""
    check = _CHECKS.get((meta or {}).get('kind'))
    return check(candidate, meta) if check else None
