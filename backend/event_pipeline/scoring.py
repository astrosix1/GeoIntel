"""
Two scores per event, both 0-100, both deterministic and explained.

  severity      — LOCAL intensity: how violent or serious it is on the ground
                  (event class, casualties, scale).
  global_impact — INTERNATIONAL significance: does it matter to the wider
                  world (states on both sides, nuclear-armed or great-power
                  parties, strategic chokepoints, escalation, how widely it's
                  reported). This drives the globe's emphasis, the critical
                  badge and the default sort.

Why: the old scores saturated. GDELT's was -GoldsteinScale*10, but Goldstein
is a fixed constant per CAMEO event code, so every "fight" (a bar brawl or a
war) scored 100 — 31% of a live hour scored >= 80. News severity started at
50 and climbed on substring hits ("war" in "software" = 80). ACLED used
30 + fatalities/2. A stabbing and a missile strike on a capital could both be
"critical", and almost none of them mattered beyond their town.

Weights, caps, the nuclear/great-power lists and strategic locations are in
config/event_filters.json ("scoring", "news_event_classes"). The breakdown
is stored in Crisis.scoring_factors so every score can be explained, and so
merging a later report re-scores from the stored inputs.
"""
import json
import re
from functools import lru_cache

from . import countries
from .config import get_config
from .keywords import has_keyword, find_keywords, strip_excluded_phrases

_VIOLENT = {'assault', 'armed_clash', 'aerial', 'mass_violence'}

_WORD_NUMBERS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'dozen': 12, 'dozens': 24, 'scores': 40, 'hundreds': 100, 'thousands': 1000,
}
_NUM = r'(\d{1,3}(?:,\d{3})+|\d+|' + '|'.join(_WORD_NUMBERS) + r')'
_VICTIMS = (r'(?:people|persons|civilians|soldiers|troops|protesters|protestors|children|others|residents|'
            r'migrants|fighters|militants|policemen|police officers|officers|villagers|worker|workers)')
_FATALITY_RES = [
    re.compile(_NUM + r'\s+(?:' + _VICTIMS + r'\s+)?(?:were\s+|have\s+been\s+|are\s+|reportedly\s+)?'
               r'(?:killed|dead|died|slain)\b', re.IGNORECASE),
    re.compile(r'\b(?:killing|kills|killed|kill)\s+(?:at\s+least\s+)?' + _NUM + r'\b', re.IGNORECASE),
    re.compile(r'\bdeath\s+toll\s+(?:rises\s+to|climbs\s+to|of|at|reaches|hits)\s+(?:at\s+least\s+)?' + _NUM,
               re.IGNORECASE),
]


def _cfg():
    return get_config().get('scoring', {})


def band(score):
    """critical / high / elevated / low — the one band definition, shared
    by the backend (briefings, economic impact, alerts) and sent to the
    frontend as severity_band / impact_band."""
    if score is None:
        return 'unknown'
    bands = _cfg().get('bands', {'critical': 80, 'high': 60, 'elevated': 35})
    if score >= bands['critical']:
        return 'critical'
    if score >= bands['high']:
        return 'high'
    if score >= bands['elevated']:
        return 'elevated'
    return 'low'


# ── inputs ─────────────────────────────────────────────────────────────────

def parse_fatalities(text):
    """Largest death count stated in the text, or None."""
    if not text:
        return None
    best = None
    for regex in _FATALITY_RES:
        for m in regex.finditer(text):
            raw = m.group(1).lower().replace(',', '')
            value = _WORD_NUMBERS.get(raw)
            if value is None:
                try:
                    value = int(raw)
                except ValueError:
                    continue
            if value < 100000 and (best is None or value > best):
                best = value
    return best


def _gdelt_class(code):
    code = str(code or '')[:3]
    root = code[:2]
    if root in ('10', '11', '12'):
        return 'verbal'
    if root == '13' or root == '16':
        return 'threat'
    if root == '14':
        return 'riot' if code == '145' else 'protest'
    if root == '15':
        return 'posture'
    if root == '17':
        return 'repression' if code in ('172', '173', '174', '175') else 'threat'
    if root == '18':
        return 'assault'
    if root == '19':
        if code in ('194', '195'):
            return 'aerial'
        return 'posture' if code == '191' else 'armed_clash'
    if root == '20':
        return 'mass_violence'
    return 'verbal'


_ACLED_SUB_CLASSES = {
    'Air/drone strike': 'aerial', 'Shelling/artillery/missile attack': 'aerial',
    'Chemical weapon': 'mass_violence', 'Suicide bomb': 'assault', 'Remote explosive/landmine/IED': 'assault',
    'Grenade': 'assault', 'Excessive force against protesters': 'repression', 'Mob violence': 'riot',
    'Violent demonstration': 'riot', 'Arrests': 'repression', 'Agreement': 'verbal',
}
_ACLED_TYPE_CLASSES = {
    'Battles': 'armed_clash', 'Explosions/Remote violence': 'assault', 'Violence against civilians': 'assault',
    'Riots': 'riot', 'Protests': 'protest', 'Strategic developments': 'posture',
}


def _news_class(text, crisis_type):
    cfg = get_config().get('news_event_classes', {})
    for cls, keywords in cfg.items():
        if cls == 'type_defaults':
            continue
        if has_keyword(text, keywords):
            return cls
    return cfg.get('type_defaults', {}).get(crisis_type, 'verbal')


def _codes_for(names):
    out = set()
    for name in names:
        record = countries.resolve(name)
        if record:
            out.add(record['code'])
    return out


@lru_cache(maxsize=1)
def _nuclear_codes():
    return frozenset(_codes_for(_cfg().get('nuclear_states', [])))


@lru_cache(maxsize=1)
def _great_power_codes():
    return frozenset(_codes_for(_cfg().get('great_powers', [])))


_STATE_FORCE_RE = re.compile(r'(?:Military|Police) Forces of ([A-Z][\w\s\-\'().]+?)(?:\s*\(|$)|Government of ([A-Z][\w\s\-\']+)')


def _acled_state_parties(actors):
    codes = set()
    for actor in actors:
        for m in _STATE_FORCE_RE.finditer(actor or ''):
            record = countries.resolve((m.group(1) or m.group(2) or '').strip())
            if record:
                codes.add(record['code'])
    return codes


def _strategic(text, lat, lon):
    from . import geo
    for place in _cfg().get('strategic_locations', []):
        if text and has_keyword(text, place.get('keywords', [])):
            return place['name']
        box = place.get('bbox')
        if box and lat is not None and lon is not None and box[0] <= lat <= box[2] and box[1] <= lon <= box[3]:
            if not place.get('at_sea_only') or geo.country_at(lat, lon) is None:
                return place['name']
    return None


def extract_features(candidate, meta):
    """The JSON-serializable inputs both scores are computed from."""
    kind = meta.get('kind')
    title = candidate.get('title') or ''
    code = meta.get('country_code')

    if kind == 'gdelt':
        from .relevance import gdelt_actors, _url_words
        g = meta.get('gdelt') or {}
        text = ' '.join(filter(None, [meta.get('headline'), title, _url_words(meta.get('url'))]))
        event_class = _gdelt_class(g.get('base_code') or g.get('event_code'))
        actors = gdelt_actors(meta)
        state_parties = {c['code'] for a in actors if a['geo'] and (c := countries.from_iso3(a['party_country']))}
        parties = {c['code'] for a in actors if (c := countries.from_iso3(a['party_country']))}
        fatalities = parse_fatalities(text)
    elif kind == 'acled':
        a = meta.get('acled') or {}
        text = title
        event_class = (_ACLED_SUB_CLASSES.get((a.get('sub_event_type') or '').strip())
                       or _ACLED_TYPE_CLASSES.get((a.get('event_type') or '').strip(), 'assault'))
        state_parties = _acled_state_parties([a.get('actor1'), a.get('actor2')])
        parties = set(state_parties)
        try:
            fatalities = int(a.get('fatalities') or 0)
        except (TypeError, ValueError):
            fatalities = 0
    else:
        text = ' '.join(filter(None, [title, meta.get('text')]))
        event_class = _news_class(strip_excluded_phrases(text.lower()), candidate.get('type'))
        parties = set(meta.get('parties') or [])
        state_parties = set(parties)
        fatalities = parse_fatalities(text)

    if code:
        parties.add(code)
    lowered = strip_excluded_phrases(text.lower())
    scale_words = _cfg().get('scale_words', {})
    found_scale = find_keywords(lowered, list(scale_words))
    return {
        'kind': kind,
        'class': event_class,
        'fatalities': fatalities,
        'scale': max((scale_words[w] for w in found_scale), default=0),
        'parties': sorted(parties),
        'interstate': len(state_parties) >= 2,
        'escalation': has_keyword(lowered, _cfg().get('escalation_terms', [])),
        'strategic': _strategic(lowered, candidate.get('latitude'), candidate.get('longitude')),
        'verified': bool(candidate.get('is_verified')),
    }


def merge_features(a, b):
    """Inputs for an event after another report of it is merged in."""
    if not a:
        return b
    if not b:
        return a
    base = _cfg().get('class_base', {})
    return {
        'kind': a.get('kind'),
        'class': max((a.get('class'), b.get('class')), key=lambda c: base.get(c, 0)),
        'fatalities': max((a.get('fatalities') or 0), (b.get('fatalities') or 0)) or a.get('fatalities'),
        'scale': max(a.get('scale', 0), b.get('scale', 0)),
        'parties': sorted(set(a.get('parties', [])) | set(b.get('parties', []))),
        'interstate': bool(a.get('interstate') or b.get('interstate')),
        'escalation': bool(a.get('escalation') or b.get('escalation')),
        'strategic': a.get('strategic') or b.get('strategic'),
        'verified': bool(a.get('verified') or b.get('verified')),
    }


# ── scores ─────────────────────────────────────────────────────────────────

def _fatality_points(fatalities):
    for threshold, points in _cfg().get('fatality_buckets', []):
        if (fatalities or 0) >= threshold:
            return points
    return 0


def score(features, source_count=1, preset_severity=None):
    """(severity, global_impact, factors). preset_severity keeps a curated
    row's own severity (sample/curated data has no scoring inputs)."""
    cfg = _cfg()
    factors = {'inputs': features, 'source_count': source_count}
    cls = features.get('class', 'verbal')
    fatalities = features.get('fatalities') or 0
    single = source_count <= 1

    if preset_severity is not None:
        severity = int(preset_severity)
        factors['severity'] = {'preset': severity}
    else:
        parts = {'class_base': cfg.get('class_base', {}).get(cls, 10),
                 'fatalities': _fatality_points(fatalities),
                 'scale': features.get('scale', 0)}
        severity = sum(parts.values())
        caps = cfg.get('severity_caps', {})
        cap = 100
        if cls == 'verbal':
            cap = min(cap, caps.get('verbal', 30))
        if cls == 'protest' and not fatalities:
            cap = min(cap, caps.get('protest_without_fatalities', 40))
        if single and not features.get('verified') and features.get('kind') in ('news', 'gdelt'):
            cap = min(cap, caps.get('single_unverified_source', 65))
        severity = max(0, min(100, severity, cap))
        parts['cap'] = cap
        factors['severity'] = parts

    imp = cfg.get('impact', {})
    parties = set(features.get('parties', []))
    nuclear = len(parties & _nuclear_codes())
    parts = {'severity_share': round(min(severity, imp.get('severity_share_max_input', 50))
                                     * imp.get('severity_share', 0.4))}
    if features.get('interstate'):
        parts['interstate'] = imp.get('interstate', 20)
        if cls in _VIOLENT:
            parts['interstate_military'] = imp.get('interstate_military', 15)
    if nuclear >= 2:
        parts['nuclear_parties'] = imp.get('two_nuclear_parties', 20)
    elif nuclear == 1:
        parts['nuclear_party'] = imp.get('nuclear_party', 12)
    if parties & _great_power_codes():
        parts['great_power'] = imp.get('great_power_party', 8)
    if features.get('strategic'):
        parts['strategic_location'] = imp.get('strategic_location', 8)
    if features.get('escalation'):
        parts['escalation'] = imp.get('escalation_term', 10)
    for threshold, points in imp.get('mass_casualties', []):
        if fatalities >= threshold:
            parts['mass_casualties'] = points
            break
    for threshold, points in imp.get('corroboration', []):
        if source_count >= threshold:
            parts['corroboration'] = points
            break
    impact = sum(parts.values())

    caps = imp.get('caps', {})
    cap = 100
    if len(parties) <= 1 and not features.get('interstate'):
        cap = min(cap, caps.get('domestic', 55))
    if single:
        cap = min(cap, caps.get('single_source', 60))
    if cls == 'verbal':
        cap = min(cap, caps.get('verbal_only', 50))
    met = {
        'interstate': bool(features.get('interstate')),
        'nuclear_party': nuclear >= 1,
        'deaths_100': fatalities >= 100,
        'sources_10': source_count >= 10,
    }
    required = [r for r in imp.get('critical_requirements', []) if met.get(r)]
    if len(required) < 2:
        cap = min(cap, cfg.get('bands', {}).get('critical', 80) - 1)
    impact = max(0, min(100, impact, cap))
    parts['cap'] = cap
    parts['critical_requirements_met'] = required
    factors['global_impact'] = parts
    return severity, impact, factors


def apply_scores(candidate, features, source_count=1):
    """Set severity, global_impact and scoring_factors on a crisis dict."""
    preset = candidate.get('severity') if features.get('kind') is None else None
    severity, impact, factors = score(features, source_count, preset_severity=preset)
    candidate['severity'] = severity
    candidate['global_impact'] = impact
    candidate['scoring_factors'] = json.dumps(factors, sort_keys=True)
    return candidate


def rescore_row(row, new_features=None):
    """Re-score a stored Crisis after merging a report into it."""
    try:
        stored = json.loads(row.scoring_factors or '{}').get('inputs')
    except ValueError:
        stored = None
    features = merge_features(stored, new_features)
    if not features:
        return
    preset = row.severity if features.get('kind') is None else None
    severity, impact, factors = score(features, row.source_count or 1, preset_severity=preset)
    row.severity, row.global_impact, row.scoring_factors = severity, impact, json.dumps(factors, sort_keys=True)
