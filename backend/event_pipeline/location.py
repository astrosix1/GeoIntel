"""
Locations: put each event in the right country, at an honest precision.

Wrong-country pins came from three places:
  - NewsAPI pinned the first known city in the text. Ambiguous names
    ("Victoria" -> Seychelles, "Georgetown" -> Guyana) and capitals used to
    mean their government ("Washington sanctions Venezuela" -> a US pin)
    both put stories in countries they weren't about.
  - GDELT's ActionGeo is any place its coder found in the article: one
    Berlin-Moscow diplomacy piece was pinned in Miami and Florida.
  - Country names were free text ("UK", "Korea, South", "Kyiv"), so the
    same country came through several ways and never matched the map.

resolve_news_location() scores every place mention instead of taking the
first. check_location() (the pipeline stage) normalizes the country through
config/countries.json, requires the coordinates to lie inside it (with a
coastal tolerance, see geo.py), requires GDELT's location to be in a
country that is actually a party to the event, and records the precision
(point/city/region/country). Country-level events are placed at the
country's centroid with a lower location_confidence.
"""
import json
import os
import re
from functools import lru_cache

from . import countries, geo
from .config import get_config

_GAZETTEER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'gazetteer.json'
)

_FILLER = {'has', 'have', 'had', 'is', 'was', 'also', 'again', 'now', 'reportedly', 'formally',
           'officially', 'on', 'publicly', 'quickly', 'swiftly', 'firmly', 'will', 'would', 'could'}
_ATTACK_VERBS = {'strikes', 'struck', 'attacks', 'attacked', 'bombs', 'bombed', 'hits', 'shells', 'shelled',
                 'invades', 'invaded', 'targets', 'targeted', 'raids', 'raided', 'pounds', 'pounded',
                 'launches', 'launched', 'fires', 'fired', 'shoots', 'downs'}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’.-]*")


def load_gazetteer():
    with open(_GAZETTEER_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)['cities']


def _cfg():
    return get_config().get('location', {})


@lru_cache(maxsize=1)
def _city_patterns():
    return [(re.compile(r'\b' + re.escape(city) + r'\b', re.IGNORECASE), city) for city in load_gazetteer()]


@lru_cache(maxsize=1)
def _gazetteer_country_codes():
    out = {}
    for city, entry in load_gazetteer().items():
        record = countries.resolve(entry['country'])
        out[city] = record['code'] if record else None
    return out


def _words_after(text, end, n=3):
    return [w.lower().strip(".'’") for w in _WORD_RE.findall(text[end:end + 80])][:n]


def _word_before(text, start):
    words = _WORD_RE.findall(text[max(0, start - 40):start])
    return words[-1].lower().strip(".'’") if words else ''


def _is_subject_of(verbs, text, end):
    """Is the mention immediately followed by one of `verbs` (allowing a
    filler word or two: "Moscow has warned", "Beijing on Tuesday said")?"""
    if text[end:end + 8].lower().startswith(('-backed', '-led', '-allied', '-aligned', '-sponsored')):
        return True
    following = [w for w in _words_after(text, end, 5) if w not in _FILLER]
    return bool(following) and following[0] in verbs


def resolve_news_location(title, description=''):
    """Best location for a news article, or None.

    Returns {'lat', 'lon', 'country', 'code', 'precision', 'place', 'parties'}
    where parties are the country codes the article names (used by the
    location stage to accept a corrected country).
    """
    cfg = _cfg()
    gov_verbs = set(cfg.get('government_verbs', []))
    preps = set(cfg.get('location_prepositions', []))
    ambiguous_cities = set(cfg.get('ambiguous_cities', []))
    ambiguous_countries = set(cfg.get('ambiguous_countries', []))
    gazetteer = load_gazetteer()
    city_codes = _gazetteer_country_codes()

    candidates = []          # dicts: kind, code, score, pos, metonym ('subject'|'object'|None), city
    mentioned = set()        # country codes named (unambiguously) in the text
    offset = 0
    for text, base in ((title or '', 3), (description or '', 1)):
        for code, start, end, kind in countries.find_in_text(text):
            before = _word_before(text, start)
            name = text[start:end].lower()
            if name in ambiguous_countries and before not in preps:
                continue
            mentioned.add(code)
            score = base - (1 if kind == 'demonym' else 0)
            if before in preps or before in _ATTACK_VERBS:
                score += 2
            if kind == 'name' and _is_subject_of(gov_verbs | _ATTACK_VERBS, text, end):
                score -= 2
            candidates.append({'kind': 'country', 'code': code, 'score': score, 'pos': offset + start})
        for pattern, city in _city_patterns():
            for m in pattern.finditer(text):
                before = _word_before(text, m.start())
                metonym = None
                if _is_subject_of(gov_verbs, text, m.end()):
                    metonym = 'subject'
                elif before in gov_verbs:
                    metonym = 'object'
                score = base + (2 if before in preps else 0)
                candidates.append({'kind': 'city', 'city': city, 'code': city_codes.get(city),
                                   'score': score, 'pos': offset + m.start(), 'metonym': metonym})
        offset += len(text) + 1

    # Ambiguous city names only count when their country is also named.
    candidates = [c for c in candidates
                  if not (c['kind'] == 'city' and c['city'] in ambiguous_cities and c['code'] not in mentioned)]
    for c in candidates:
        if c['kind'] == 'city' and not c['metonym'] and c['code'] in mentioned:
            c['score'] += 2

    placeable = [c for c in candidates if c['code'] and not (c['kind'] == 'city' and c['metonym'])]
    parties = sorted(mentioned | {c['code'] for c in candidates if c['kind'] == 'city' and c['code']})

    if placeable:
        best = max(placeable, key=lambda c: (c['score'], c['kind'] == 'city', -c['pos']))
    else:
        # Only capitals-as-governments ("Washington warns Tehran"): place at
        # the country of the party acted upon, at country precision.
        metonyms = [c for c in candidates if c['kind'] == 'city' and c['code']]
        if not metonyms:
            return None
        objects = [c for c in metonyms if c['metonym'] == 'object']
        pick = min(objects or metonyms, key=lambda c: c['pos'])
        best = {'kind': 'country', 'code': pick['code']}

    record = countries.by_code(best['code'])
    if not record:
        return None
    if best['kind'] == 'city':
        entry = gazetteer[best['city']]
        return {'lat': entry['lat'], 'lon': entry['lon'], 'country': record['name'], 'code': record['code'],
                'precision': 'city', 'place': best['city'].title(), 'parties': parties}
    lat, lon = record['centroid']
    return {'lat': lat, 'lon': lon, 'country': record['name'], 'code': record['code'],
            'precision': 'country', 'place': record['name'], 'parties': parties}


# ── pipeline stage ─────────────────────────────────────────────────────────

_GDELT_PRECISION = {'1': 'country', '2': 'region', '5': 'region', '3': 'city', '4': 'city'}


def resolve_geo_fullname(full_name):
    """Country record from a GDELT-style "Place, Admin1, Country" name. The
    country itself may contain a comma ("Korea, South"), so try the last
    two segments joined before the last one alone."""
    parts = [p.strip() for p in (full_name or '').split(',') if p.strip()]
    if not parts:
        return None
    if len(parts) >= 2:
        record = countries.resolve(', '.join(parts[-2:]))
        if record:
            return record
    return countries.resolve(parts[-1])


def _gdelt_parties(meta):
    # Only actors that are really a country's state or a typed group from it
    # (not a place name GDELT coded as a country) make that country a party.
    from .relevance import gdelt_actors
    parties = set()
    for actor in gdelt_actors(meta):
        record = countries.from_iso3(actor['party_country'])
        if record:
            parties.add(record['code'])
    return parties


def _relocate_gdelt(candidate, meta, parties):
    """ActionGeo is in a country that isn't party to the event: use an
    actor's own geo if that is in a party country, else the single party's
    centroid. Returns True if relocated."""
    for alt in meta.get('alt_geos') or []:
        record = resolve_geo_fullname(alt.get('full_name'))
        try:
            lat, lon = float(alt.get('lat')), float(alt.get('lon'))
        except (TypeError, ValueError):
            continue
        if record and record['code'] in parties and not (lat == 0 and lon == 0):
            candidate['latitude'], candidate['longitude'] = lat, lon
            candidate['country'] = record['name']
            meta['precision'] = _GDELT_PRECISION.get(str(alt.get('type')), 'city')
            meta['place_full_name'] = alt.get('full_name')
            return True
    if len(parties) == 1:
        record = countries.by_code(next(iter(parties)))
        candidate['latitude'], candidate['longitude'] = record['centroid']
        candidate['country'] = record['name']
        meta['precision'] = 'country'
        meta['place_full_name'] = record['name']
        return True
    return False


def check_location(candidate, meta):
    """Pipeline stage. Returns None (keep, possibly corrected) or a reason:
    unknown_country, geo_actor_mismatch, coords_country_mismatch."""
    cfg = _cfg()
    kind = meta.get('kind')

    record = None
    if kind == 'gdelt':
        record = resolve_geo_fullname(meta.get('place_full_name'))
        parties = _gdelt_parties(meta)
        if record is None:
            record = countries.resolve(candidate['country'])
        if parties and (record is None or record['code'] not in parties):
            if not _relocate_gdelt(candidate, meta, parties):
                return 'geo_actor_mismatch'
            record = countries.resolve(candidate['country'])
    else:
        parties = set(meta.get('parties') or ())
        record = countries.resolve(candidate['country'])
        if kind == 'acled' and record:
            parties.add(record['code'])

    lat, lon = candidate['latitude'], candidate['longitude']
    precision = meta.get('precision') or 'city'
    tolerance = cfg.get('point_tolerance_km', 25)

    if precision != 'country' or record is None:
        actual = geo.country_at(lat, lon)
        if record is None:
            if actual is None:
                return 'unknown_country'
            record = countries.by_code(actual)
        elif not geo.point_in_country(lat, lon, record['code'], tolerance):
            if actual and (kind is None or actual in parties):
                record = countries.by_code(actual)       # coordinates are right, the name was wrong
            elif actual is None and geo.distance_km(
                    record['code'], lat, lon, cap_km=cfg.get('offshore_km', 150) + 1) <= cfg.get('offshore_km', 150):
                pass                                      # at sea near the country (strait, coast)
            else:
                return 'coords_country_mismatch'

    if precision == 'country':
        candidate['latitude'], candidate['longitude'] = record['centroid']
    candidate['country'] = record['name']
    confidence = cfg.get('confidence_by_precision', {}).get(precision)
    if confidence is not None:
        candidate['location_confidence'] = confidence
    meta['country_code'] = record['code']
    meta['location_precision'] = precision
    return None
