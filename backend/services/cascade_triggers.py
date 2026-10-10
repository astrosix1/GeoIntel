"""
The cascade triggers: what a user can ask, as data. Each template says in plain words what it assumes and which engine runs it
(a country that stops supplying, a country that stops buying, or both). run_template() runs them and merges the two directions into
one effect per country, keeping every piece of evidence.

Five templates work today. Chokepoint closures need the curated chokepoint table (stage 3 of docs/cascade-plan.md) and are not offered
until it exists, so nothing here pretends to model them.
"""
from services import cascade_engine as engine
from services.cascade_engine import COMMODITY_TERMS, HIGH, LOW, MODERATE, UnknownCountry

COMMODITY_LABELS = {
    'gas': 'Natural gas', 'oil': 'Oil', 'coal': 'Coal', 'grain': 'Grain', 'veg_oils': 'Vegetable oils', 'fertilizers': 'Fertilizers',
    'iron_ore': 'Iron ore', 'copper': 'Copper', 'aluminium': 'Aluminium', 'chips': 'Computer chips',
}

# key -> label, what it assumes, which directions it runs, and whether a commodity is optional or required
TEMPLATES = {
    'attack': {
        'label': 'A country is attacked or invaded',
        'assumes': 'The country can no longer trade normally: it stops supplying its exports and stops buying its imports.',
        'modes': ('supply_loss', 'demand_loss'), 'commodity': 'none',
    },
    'embargo': {
        'label': 'Sanctions or an embargo on a country',
        'assumes': 'Trade with the country is cut, in both directions, for everything or for one commodity.',
        'modes': ('supply_loss', 'demand_loss'), 'commodity': 'optional',
    },
    'export_ban': {
        'label': 'A country bans exports of a commodity',
        'assumes': 'The country stops selling the commodity abroad; what it buys is unchanged.',
        'modes': ('supply_loss',), 'commodity': 'required',
    },
    'hazard': {
        'label': 'A disaster hits a key producer',
        'assumes': 'The country\'s output of everything, or of one commodity, is lost for a time (a quake, flood, storm or similar).',
        'modes': ('supply_loss',), 'commodity': 'optional',
    },
    'collapse': {
        'label': 'A government collapses',
        'assumes': 'The country\'s trade breaks down in both directions while authority is contested.',
        'modes': ('supply_loss', 'demand_loss'), 'commodity': 'none',
    },
}

# Event types in the news feed -> the template that fits best when a user starts from an event.
EVENT_TEMPLATES = {'conflict': 'attack', 'military': 'attack', 'proxy': 'attack', 'civil_unrest': 'collapse', 'economic': 'embargo',
                   'trade_war': 'embargo', 'resource': 'export_ban'}
_RANK = {HIGH: 0, MODERATE: 1, LOW: 2}


class BadTrigger(ValueError):
    pass


def options():
    """What the picker offers: templates, commodities, nothing else."""
    return {
        'templates': [{'key': k, 'label': t['label'], 'assumes': t['assumes'], 'commodity': t['commodity']} for k, t in TEMPLATES.items()],
        'commodities': [{'key': k, 'label': COMMODITY_LABELS.get(k, k)} for k in COMMODITY_TERMS],
    }


def trigger_for_event(event_type, country_iso):
    """(template, note) for an event: the template that fits its type, and a plain sentence saying what was assumed."""
    template = EVENT_TEMPLATES.get(event_type or '', 'attack')
    return template, (f"Started from an event of type \"{event_type}\": treated as \"{TEMPLATES[template]['label'].lower()}\" in {country_iso}. "
                      f"Change the trigger in the Cascade workspace to ask something else.")


def _merge(runs):
    """One effect per country from several directions: the highest exposure, every mechanism, the soonest horizon, all evidence."""
    by = {}
    for result in runs:
        for e in result['effects']:
            cur = by.get(e['iso'])
            if cur is None:
                by[e['iso']] = {**e, 'mechanisms': [e['mechanism']], 'evidence': list(e['evidence']), 'caveats': list(e['caveats'])}
                continue
            if _RANK[e['exposure']] < _RANK[cur['exposure']]:
                cur['exposure'] = e['exposure']
            cur['mechanisms'].append(e['mechanism'])
            cur['evidence'].extend(e['evidence'])
            cur['caveats'].extend(c for c in e['caveats'] if c not in cur['caveats'])
            cur['driver_percent'] = max(cur['driver_percent'], e['driver_percent'])
    effects = sorted(by.values(), key=lambda e: (_RANK[e['exposure']], -e['driver_percent'], e['name']))
    for e in effects:
        e['mechanism'] = e['mechanisms'][0]
    return effects


def run_template(graph, template, country, commodity=None, table=None):
    """Run a template for a country (ISO-2) and optional commodity. Raises BadTrigger for input that does not fit the template and
    UnknownCountry for a country the graph has no data on."""
    spec = TEMPLATES.get(template)
    if spec is None:
        raise BadTrigger(f'unknown trigger: {template}')
    if spec['commodity'] == 'required' and not commodity:
        raise BadTrigger('this trigger needs a commodity')
    if spec['commodity'] == 'none':
        commodity = None
    if commodity is not None and commodity not in COMMODITY_TERMS:
        raise BadTrigger(f'unknown commodity: {commodity}')
    modes, assumes = spec['modes'], spec['assumes']
    if commodity and 'demand_loss' in modes:
        # With one commodity the question is about that commodity leaving the country; the buying side has no commodity-level data.
        modes = tuple(m for m in modes if m != 'demand_loss')
        assumes = f"The country's exports of {COMMODITY_LABELS.get(commodity, commodity).lower()} are cut off; what it buys is unchanged."
    runs = [engine.run(graph, {'kind': mode, 'country': country, 'commodity': commodity}, table) for mode in modes]
    base = runs[0]
    effects = _merge(runs)
    return {
        'trigger': {'template': template, 'label': spec['label'], 'country': base['trigger']['country'],
                    'country_name': base['trigger']['country_name'], 'commodity': commodity,
                    'commodity_label': COMMODITY_LABELS.get(commodity) if commodity else None},
        'assumes': assumes,
        'effects': effects,
        'counts': {level: sum(1 for e in effects if e['exposure'] == level) for level in (HIGH, MODERATE, LOW)},
        'notes': [n for r in runs for n in r['notes']],
        'method': base['method'],
        'not_modelled': base['not_modelled'],
        'data': base['data'],
    }
