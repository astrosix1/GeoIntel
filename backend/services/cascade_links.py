"""
The links beyond trade for the cascade: people (where a country's emigrants already live), treaties (mutual-defence commitments), and
two kinds of context (sanctions already in place, how much of a mineral a country produces). Each effect carries its evidence; the
thresholds are stated in METHOD below and shown to the user. Treaty effects are obligations, never predictions of what a member will do.
"""
import json
from functools import lru_cache
from pathlib import Path

from services import cascade_engine as engine

DATA = Path(__file__).resolve().parent.parent / 'data'

# People: X-born residents of a country, as a share of that country's population.
DIASPORA_HIGH_PCT = 1.0
DIASPORA_MODERATE_PCT = 0.3
DIASPORA_LISTED_PCT = 0.05
DIASPORA_MIN_PEOPLE = 10_000       # a handful of people is not an exposure

METHOD = {
    'people': (f'Where emigrants of the country already live: High when they are {DIASPORA_HIGH_PCT:g}% or more of the host country\'s population, '
               f'Moderate from {DIASPORA_MODERATE_PCT:g}%, Low from {DIASPORA_LISTED_PCT:g}% (at least {DIASPORA_MIN_PEOPLE:,} people).'),
    'treaty': 'Other parties to a mutual-defence treaty with the country are Moderate: they have a commitment, and each decides for itself what to do.',
}


@lru_cache(maxsize=1)
def _migration():
    return json.loads((DATA.parent / 'data_sources' / 'migration_origins.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _treaties():
    try:
        return json.loads((DATA / 'cascade' / 'treaties.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'treaties': {}, 'last_reviewed': None}


@lru_cache(maxsize=1)
def _sanctions():
    try:
        return json.loads((DATA / 'cascade' / 'sanctions.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'measures': {}, 'last_reviewed': None}


@lru_cache(maxsize=1)
def _minerals():
    try:
        return json.loads((DATA / 'country' / 'minerals.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'countries': {}}


def _level(percent):
    if percent >= DIASPORA_HIGH_PCT:
        return engine.HIGH
    if percent >= DIASPORA_MODERATE_PCT:
        return engine.MODERATE
    return engine.LOW if percent >= DIASPORA_LISTED_PCT else None


def diaspora(graph, iso):
    """Effects on the countries where this country's emigrants already live (networks that refugees and migrants use), from the UN
    migrant-stock table and World Bank population. Returns [] when the table has nothing for the country."""
    emigrants = ((_migration()['countries'].get(iso) or {}).get('emigrants') or {})
    effects = []
    for dest, count in emigrants.get('destinations', []):
        node = graph['countries'].get(dest)
        if dest == iso or not node or not node.get('population') or count < DIASPORA_MIN_PEOPLE:
            continue
        percent = 100.0 * count / node['population']
        level = _level(percent)
        if level is None:
            continue
        name = graph['countries'][iso]['name']
        effects.append({
            'iso': dest, 'name': node['name'], 'exposure': level, 'mechanism': 'People: existing ties to the country', 'horizon': 'months',
            'driver_percent': round(percent, 2),
            'evidence': [{'text': f"{count:,} people born in {name} live in {node['name']}, about {percent:.2g}% of its population.",
                          'source': 'UN DESA migrant stock and World Bank population', 'as_of': 2024}],
            'caveats': ['People born in the country already live there; this shows where networks for refuge exist, not how many people would move.'],
        })
    return effects


def treaty_effects(graph, iso):
    """Other parties to a mutual-defence treaty with this country, as Moderate effects with the treaty's own words."""
    table = _treaties()
    out = {}
    for key, treaty in table['treaties'].items():
        if iso not in treaty['members']:
            continue
        for other in treaty['members']:
            node = graph['countries'].get(other)
            if other == iso or not node:
                continue
            name = graph['countries'][iso]['name'] if iso in graph['countries'] else iso
            text = f"{node['name']} and {name} are both parties to {treaty['label']}: {treaty['clause']}."
            entry = out.setdefault(other, {
                'iso': other, 'name': node['name'], 'exposure': engine.MODERATE, 'mechanism': 'Treaty: mutual-defence commitment', 'horizon': 'days',
                'driver_percent': 0.0, 'evidence': [], 'caveats': ['A commitment is not an automatic response: each party decides what action to take.']})
            entry['evidence'].append({'text': text, 'source': treaty['source'], 'as_of': None})
            if treaty.get('note'):
                entry['caveats'].append(treaty['note'])
    return sorted(out.values(), key=lambda e: e['name'])


def sanctions_note(iso):
    """A plain sentence about long-standing sanctions already on the country, or None."""
    items = _sanctions()['measures'].get(iso)
    if not items:
        return None
    parts = '; '.join(f"{m['by']} since {m['since']} ({m['scope']})" for m in items)
    return f"Measures already in place (not exhaustive, reviewed {_sanctions().get('last_reviewed')}): {parts}."


_USGS = {'copper': 'Copper', 'aluminium': 'Aluminum', 'iron_ore': 'Iron ore'}


def producer_note(iso, commodity):
    """How much of the world's mineral a country produces (USGS), or None."""
    name = _USGS.get(commodity)
    for row in (_minerals()['countries'].get(iso) or []):
        if name and row.get('commodity') == name and row.get('world_share') is not None:
            return f"{name}: the country produced {row['world_share']:g}% of world output (rank {row.get('rank')}, USGS {row.get('year')})."
    return None
