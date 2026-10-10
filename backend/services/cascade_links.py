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


def _years(graph):
    """The range of years the Factbook's partner shares are for in this graph, as text."""
    years = sorted({y for c in graph['countries'].values() for y in (c.get('partners_as_of') or {}).values() if isinstance(y, int)})
    return 'unknown years' if not years else str(years[0]) if len(years) == 1 else f'{years[0]} to {years[-1]}'


def sources(graph, trade_table):
    """The data behind Cascade, each with what it is used for and how fresh it is, for the methods page."""
    chokepoints, treaties, sanctions = _chokepoints_reviewed(), _treaties().get('last_reviewed'), _sanctions().get('last_reviewed')
    out = [
        {'name': 'CIA World Factbook', 'used_for': 'Top trading partners and their shares, main exports, and each country\'s gas and oil production and use.',
         'fresh': f"Partner shares are for {_years(graph)} depending on the country; read for this build on {(graph.get('built_at') or '')[:10] or 'an unknown date'}."},
        {'name': 'UN Comtrade (public preview)', 'used_for': 'Each country\'s imports of oil, gas, coal, grain, vegetable oils, fertilizers, iron ore, copper, aluminium and chips, by supplier.',
         'fresh': 'The newest of 2022, 2023 and 2021 that has data for the country.' if trade_table else 'Not loaded in this build: the Factbook\'s all-goods shares are used instead.'},
        {'name': 'UN DESA migrant stock and World Bank population', 'used_for': 'Where each country\'s emigrants already live, as a share of the host country\'s population.',
         'fresh': 'Migrant stock for 2024; population is the latest World Bank value.'},
        {'name': 'USGS Mineral Commodity Summaries', 'used_for': 'How much of the world\'s copper, aluminium and iron ore a country produces.', 'fresh': 'The 2025 summaries.'},
        {'name': 'US Energy Information Administration', 'used_for': 'Oil and LNG flows through the Strait of Hormuz and Bab el-Mandeb (hand-curated table).',
         'fresh': f'Figures for 2023 and 2024; table last reviewed {chokepoints}.'},
        {'name': 'NATO, CSTO and the US Department of State', 'used_for': 'Mutual-defence treaty members (hand-curated table).', 'fresh': f'Last reviewed {treaties}.'},
        {'name': 'EU Council, US Treasury, UN Security Council', 'used_for': 'Long-standing sanctions already in place (hand-curated, not exhaustive).', 'fresh': f'Last reviewed {sanctions}.'},
    ]
    return out


def _chokepoints_reviewed():
    from services import cascade_chokepoints
    return cascade_chokepoints.load().get('last_reviewed')
