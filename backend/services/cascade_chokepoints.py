"""
Shipping chokepoints for the cascade: a closure is run as a loss of supply from the countries that ship through it, each weighted by how
much of its trade is stated to use the route. The table is hand-curated and dated (backend/data/cascade/chokepoints.json); a country's
use of a route is marked "stated" when the source says so and "assumed" when it is inferred from geography, and the result says which.
"""
import json
from functools import lru_cache
from pathlib import Path

from services import cascade_engine as engine

PATH = Path(__file__).resolve().parent.parent / 'data' / 'cascade' / 'chokepoints.json'
_RANK = {engine.HIGH: 0, engine.MODERATE: 1, engine.LOW: 2}
THROUGH_TEXT = {
    'all': 'All of its exports of this are taken to pass through the route.',
    'most': 'Most of its exports of this pass through the route; a bypass carries part.',
    'part': 'Only part of its exports of this pass through the route; a bypass or another route carries the rest, so exposure is capped at Moderate.',
}


@lru_cache(maxsize=1)
def load():
    try:
        return json.loads(PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'chokepoints': {}, 'last_reviewed': None}


def _caveat(exporter):
    basis = '' if exporter['basis'] == 'stated' else ' This use of the route is assumed from geography, not stated by the source.'
    return f"{THROUGH_TEXT[exporter['through']]}{basis}"


def options():
    table = load()
    return [{'key': k, 'label': v['label'], 'summary': v['summary']} for k, v in table['chokepoints'].items()]


def run(graph, key, commodity=None, trade=None):
    """The effects of closing a chokepoint: one entry per country, importers losing supply and the exporters losing their route.
    Returns (effects, notes). Raises ValueError for an unknown chokepoint."""
    table = load()
    spec = table['chokepoints'].get(key)
    if spec is None:
        raise ValueError(f'unknown chokepoint: {key}')
    by, notes = {}, [f"{spec['label']}: {spec['summary']} ({spec['source']}, {spec['year']}). Chokepoint table last reviewed {table.get('last_reviewed')}."]

    def add(effect):
        cur = by.get(effect['iso'])
        if cur is None:
            by[effect['iso']] = {**effect, 'mechanisms': [effect['mechanism']], 'evidence': list(effect['evidence']), 'caveats': list(effect['caveats'])}
            return
        if _RANK[effect['exposure']] < _RANK[cur['exposure']]:
            cur['exposure'] = effect['exposure']
        cur['mechanisms'].append(effect['mechanism'])
        cur['evidence'].extend(effect['evidence'])
        cur['caveats'].extend(c for c in effect['caveats'] if c not in cur['caveats'])
        cur['driver_percent'] = max(cur['driver_percent'], effect['driver_percent'])

    usable = []
    for exporter in spec['exporters']:
        iso = exporter['iso']
        goods = [c for c in exporter['commodities'] if commodity in (None, c)]
        if iso in graph['countries'] and goods:
            usable.append((exporter, goods))
    # The exporters' own route loss goes in first, so it leads each country's evidence.
    for exporter, goods in usable:
        name = graph['countries'][exporter['iso']]['name']
        add({'iso': exporter['iso'], 'name': name, 'exposure': engine.MODERATE if exporter['through'] == 'part' else engine.HIGH,
             'mechanism': 'Export route closed', 'horizon': 'days',
             'driver_percent': 100.0 if exporter['through'] == 'all' else 50.0 if exporter['through'] == 'most' else 25.0,
             'evidence': [{'text': f"{name}: {exporter['note']}", 'source': spec['source'], 'as_of': spec['year']}], 'caveats': [_caveat(exporter)]})
    for exporter, goods in usable:
        iso, name, cap = exporter['iso'], graph['countries'][exporter['iso']]['name'], exporter['through'] == 'part'
        for good in goods:
            result = engine.run(graph, {'kind': 'supply_loss', 'country': iso, 'commodity': good}, trade)
            for effect in result['effects']:
                effect = {**effect, 'evidence': [{**e} for e in effect['evidence']],
                          'caveats': list(effect['caveats']) + [f"Reached through {name}'s exports via the {spec['label']}. {_caveat(exporter)}"]}
                if cap and effect['exposure'] == engine.HIGH:
                    effect['exposure'] = engine.MODERATE
                add(effect)
    effects = sorted(by.values(), key=lambda e: (_RANK[e['exposure']], -e['driver_percent'], e['name']))
    for e in effects:
        e['mechanism'] = e['mechanisms'][0]
    return effects, notes
