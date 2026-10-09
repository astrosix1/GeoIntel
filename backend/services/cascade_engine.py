"""
The cascade engine: who is exposed when a country stops supplying, or stops buying. Deterministic and rule-based. Every effect
carries the numbers and the source it rests on, the mechanism that links it to the trigger, and how soon it would bite.
Exposure is High, Moderate or Low from the stated thresholds below. There are no probabilities and no unexplained constants:
a rule is either a threshold on a published share, or it is not here.

Stage 0 has two mechanisms, trade dependence and energy dependence, one step out from the trigger. Later stages add minerals,
people, treaties and chokepoints (see docs/cascade-plan.md).

Run it by hand:  python -m services.cascade_engine supply_loss RU --commodity gas
"""
import argparse
import json

from services import cascade_trade

HIGH, MODERATE, LOW = 'High', 'Moderate', 'Low'
_ORDER = {HIGH: 0, MODERATE: 1, LOW: 2}

# --- the rules, in one place so they can be read and argued with ---------------------------------------------------
TRADE_HIGH_PCT = 15.0          # a partner that is at least this share of a country's imports (or exports) is a High exposure
TRADE_MODERATE_PCT = 5.0       # at least this share: Moderate
TRADE_LISTED_PCT = 2.0         # at least this share: listed as Low; smaller shares are left out as negligible
DEPENDENCE_HIGH_PCT = 50.0     # a country that imports at least this share of the fuel it uses is highly dependent
DEPENDENCE_MODERATE_PCT = 20.0 # at least this share: moderately dependent; below it the country mostly supplies itself
SURPLUS_FACTOR = 1.1           # a country counts as a net exporter of a fuel when it produces 10% more than it uses

COMMODITY_TERMS = {
    'gas': ('natural gas', 'gas', 'lng', 'liquefied'),
    'oil': ('petroleum', 'crude', 'oil', 'refined'),
    'grain': ('wheat', 'grain', 'corn', 'maize', 'barley', 'cereal', 'sunflower', 'rice'),
    'coal': ('coal',),
    'veg_oils': ('sunflower', 'palm oil', 'soybean oil', 'vegetable oil'),
    'fertilizers': ('fertilizer', 'fertiliser', 'potash', 'ammonia', 'urea'),
    'iron_ore': ('iron ore',),
    'copper': ('copper',),
    'aluminium': ('aluminum', 'aluminium', 'bauxite', 'alumina'),
    'chips': ('semiconductor', 'integrated circuit', 'electronic'),
}
FUELS = ('gas', 'oil')
HORIZONS = {'gas': 'days to weeks', 'oil': 'weeks', 'coal': 'weeks', 'grain': 'weeks to months', 'veg_oils': 'weeks to months',
            'fertilizers': 'months', 'iron_ore': 'months', 'copper': 'months', 'aluminium': 'months', 'chips': 'months', None: 'weeks to months'}

# Commodity-level rules, used when the bundled UN Comtrade table has the importer: shares are of the importer's imports of that
# commodity, so the bar is higher than for all goods, and tiny import bills are ignored.
COMMODITY_SHARE_HIGH_PCT = 25.0
COMMODITY_SHARE_MODERATE_PCT = 10.0
COMMODITY_SHARE_LISTED_PCT = 3.0
MIN_IMPORT_USD = 50e6

NOT_MODELLED = [
    'Prices and markets: a supply loss moves prices before it moves quantities, and this does not model that.',
    'Decisions: how governments, companies and militaries respond is not modelled.',
    'Substitutes and stockpiles: where another supplier or a reserve exists, exposure may be lower than shown.',
    'Only the top five trading partners of each country are published, so a smaller dependence can be missing.',
    'Partner shares are for all goods unless a fuel balance is shown, and are a few years old.',
]


class UnknownCountry(ValueError):
    pass


def trade_level(percent):
    """High, Moderate or Low for a partner's share of imports or exports, or None when the share is negligible."""
    if percent >= TRADE_HIGH_PCT:
        return HIGH
    if percent >= TRADE_MODERATE_PCT:
        return MODERATE
    if percent >= TRADE_LISTED_PCT:
        return LOW
    return None


def fuel_dependence(fuels, fuel):
    """{'percent', 'text'} for the share of a fuel a country imports, from its published production and consumption (or imports),
    or None when the Factbook does not publish enough."""
    data = (fuels or {}).get(fuel) or {}
    consumption = (data.get('consumption') or {}).get('value')
    if not consumption:
        return None
    imports = (data.get('imports') or {}).get('value')
    production = (data.get('production') or {}).get('value')
    year = (data.get('consumption') or {}).get('as_of')
    if imports is not None:
        percent = min(100.0, 100.0 * imports / consumption)
        text = f'imports about {percent:.0f}% of the {_fuel_label(fuel)} it uses (imports {_amount(imports, fuel)} against use of {_amount(consumption, fuel)})'
    elif production is not None:
        percent = max(0.0, 100.0 * (consumption - production) / consumption)
        text = (f'imports about {percent:.0f}% of the {_fuel_label(fuel)} it uses '
                f'(production {_amount(production, fuel)} against use of {_amount(consumption, fuel)})')
    else:
        return None
    return {'percent': percent, 'text': text, 'as_of': year}


def _fuel_label(fuel):
    return 'natural gas' if fuel == 'gas' else 'oil products'


def _amount(value, fuel):
    if fuel == 'gas':
        return f'{value / 1e9:,.1f} billion cubic metres a year'
    return f'{value / 1e6:,.2f} million barrels a day' if value >= 1e6 else f'{value / 1e3:,.0f} thousand barrels a day'


def supplies(entry, commodity):
    """(True/False, reason): whether the country is shown to supply a commodity, from its listed export goods and, for fuels, its
    production against its own use."""
    terms = COMMODITY_TERMS.get(commodity, ())
    listed = [c for c in entry.get('export_commodities', []) if any(t in c for t in terms)]
    if listed:
        return True, f"its main exports include {', '.join(listed[:3])}"
    if commodity in FUELS:
        data = (entry.get('fuels') or {}).get(commodity) or {}
        production = (data.get('production') or {}).get('value')
        consumption = (data.get('consumption') or {}).get('value')
        if production and consumption and production > SURPLUS_FACTOR * consumption:
            return True, f'it produces more {_fuel_label(commodity)} than it uses'
    return False, None


def _evidence(text, as_of):
    return {'text': text, 'source': 'CIA World Factbook', 'as_of': as_of}


def _find(partners, iso):
    return next((p for p in partners if p['iso'] == iso and not p['under'] and p['percent'] > 0), None)


def _energy_level(share, dependence):
    """Exposure of an importer to the loss of a fuel supplier: its dependence on imported fuel decides how much a supplier's share
    matters."""
    if dependence is None:
        return MODERATE if share >= TRADE_MODERATE_PCT else (LOW if share >= TRADE_LISTED_PCT else None)
    if dependence < DEPENDENCE_MODERATE_PCT:
        return LOW if share >= TRADE_MODERATE_PCT else None            # mostly supplies itself
    if (share >= TRADE_HIGH_PCT) or (share >= TRADE_MODERATE_PCT and dependence >= DEPENDENCE_HIGH_PCT):
        return HIGH
    return MODERATE if share >= TRADE_LISTED_PCT else None


def _commodity_level(share, dependence):
    """Exposure of an importer to losing a supplier of one commodity: the supplier's share of its imports of it, tempered for fuels by
    how much of the fuel the country imports at all."""
    if dependence is not None and dependence < DEPENDENCE_MODERATE_PCT:
        return LOW if share >= COMMODITY_SHARE_MODERATE_PCT else None            # mostly supplies itself
    if share >= COMMODITY_SHARE_HIGH_PCT or (dependence is not None and dependence >= DEPENDENCE_HIGH_PCT and share >= COMMODITY_SHARE_MODERATE_PCT):
        return HIGH
    if share >= COMMODITY_SHARE_MODERATE_PCT:
        return MODERATE
    return LOW if share >= COMMODITY_SHARE_LISTED_PCT else None


def _supply_loss_traded(graph, table, iso, commodity):
    """Supply loss from the commodity-level table. Importers come from the table; names and fuel balances from the graph."""
    source_name = graph['countries'][iso]['name']
    effects, notes = [], []
    label = ', '.join(table['commodities'][g]['label'].lower() for g in cascade_trade.GROUPS[commodity] if g in table['commodities'])
    for code in sorted(table['imports']):
        if code == iso or code not in graph['countries']:
            continue
        data = cascade_trade.combined(table, code, commodity)
        if not data or data['total'] < MIN_IMPORT_USD:
            continue
        share = data['shares'].get(iso)
        if not share:
            continue
        entry = graph['countries'][code]
        dep = fuel_dependence(entry.get('fuels'), commodity) if commodity in FUELS else None
        level = _commodity_level(share, dep['percent'] if dep else None)
        if level is None:
            continue
        evidence = [{'text': f"{source_name} supplied {share:g}% of {entry['name']}'s imports of {label} (${data['total'] / 1e9:,.2f} billion in all).",
                     'source': 'UN Comtrade', 'as_of': data['year']}]
        caveats = []
        if dep:
            evidence.append(_evidence(f"{entry['name']} {dep['text']}.", dep['as_of']))
        elif commodity in FUELS:
            caveats.append(f"The Factbook publishes no {_fuel_label(commodity)} balance for {entry['name']}, so its dependence is not known.")
        effects.append({'iso': code, 'name': entry['name'], 'exposure': level, 'mechanism': f'Supply loss: {commodity.replace("_", " ")} import dependence',
                        'horizon': HORIZONS.get(commodity, HORIZONS[None]), 'driver_percent': share, 'evidence': evidence, 'caveats': caveats})
    if not effects:
        notes.append(f"No importer in the trade table gets {COMMODITY_SHARE_LISTED_PCT:g}% or more of its {label} from {source_name}.")
    else:
        notes.append(f'Shares are of each country\'s imports of {label}, from UN Comtrade; importers with under ${MIN_IMPORT_USD / 1e6:,.0f} million of imports are left out.')
    return effects, notes


def _supply_loss(graph, iso, commodity, table=None):
    if table and commodity in cascade_trade.GROUPS:
        return _supply_loss_traded(graph, table, iso, commodity)
    return _supply_loss_factbook(graph, iso, commodity)


def _supply_loss_factbook(graph, iso, commodity):
    countries = graph['countries']
    source = countries[iso]
    effects, notes = [], []
    if commodity:
        ok, reason = supplies(source, commodity)
        if not ok:
            notes.append(f"{source['name']} is not shown to export {commodity} (its listed main exports and its fuel balance do not say so), so no effects are listed.")
            return effects, notes
        notes.append(f"{source['name']} is treated as a supplier of {commodity} because {reason}.")
    for code, entry in countries.items():
        if code == iso:
            continue
        link = _find(entry['import_partners'], iso)
        if not link:
            continue
        as_of = entry['partners_as_of'].get('imports')
        evidence = [_evidence(f"{source['name']} supplies {link['percent']:g}% of {entry['name']}'s imports.", as_of)]
        caveats = []
        if commodity in FUELS:
            dep = fuel_dependence(entry.get('fuels'), commodity)
            level = _energy_level(link['percent'], dep['percent'] if dep else None)
            mechanism = 'Supply loss: energy import dependence'
            if dep:
                evidence.append(_evidence(f"{entry['name']} {dep['text']}.", dep['as_of']))
            else:
                caveats.append(f"The Factbook publishes no {_fuel_label(commodity)} balance for {entry['name']}, so its dependence is not known.")
            caveats.append('The partner share is for all imports; bilateral fuel flows are not published in open data.')
        else:
            level = trade_level(link['percent'])
            mechanism = 'Supply loss: trade dependence'
            if commodity and level == HIGH:
                level = MODERATE
                caveats.append(f'The share is for all imports, not for {commodity} alone, so exposure is capped at Moderate.')
            elif commodity:
                caveats.append(f'The share is for all imports, not for {commodity} alone.')
        if level is None:
            continue
        effects.append({'iso': code, 'name': entry['name'], 'exposure': level, 'mechanism': mechanism,
                        'horizon': HORIZONS.get(commodity, HORIZONS[None]), 'driver_percent': link['percent'],
                        'evidence': evidence, 'caveats': caveats})
    return effects, notes


def _demand_loss(graph, iso, commodity):
    countries = graph['countries']
    buyer = countries[iso]
    effects, notes = [], []
    for code, entry in countries.items():
        if code == iso:
            continue
        link = _find(entry['export_partners'], iso)
        if not link:
            continue
        if commodity:
            ok, _ = supplies(entry, commodity)
            if not ok:
                continue
        level = trade_level(link['percent'])
        if level is None:
            continue
        as_of = entry['partners_as_of'].get('exports')
        caveats = ['The share is for all exports.'] if commodity else []
        effects.append({'iso': code, 'name': entry['name'], 'exposure': level, 'mechanism': 'Demand loss: export dependence',
                        'horizon': 'weeks to months', 'driver_percent': link['percent'],
                        'evidence': [_evidence(f"{buyer['name']} takes {link['percent']:g}% of {entry['name']}'s exports.", as_of)],
                        'caveats': caveats})
    return effects, notes


KINDS = {'supply_loss': _supply_loss, 'demand_loss': lambda graph, iso, commodity, table=None: _demand_loss(graph, iso, commodity)}


def run(graph, trigger, table=None):
    """Run a trigger over a graph. `trigger` is {'kind': 'supply_loss' | 'demand_loss', 'country': ISO2, 'commodity': optional}.
    Returns the effects ranked High first, with the method, what is not modelled, and which data it used."""
    kind, iso, commodity = trigger.get('kind'), (trigger.get('country') or '').upper(), trigger.get('commodity')
    if kind not in KINDS:
        raise ValueError(f"unknown trigger kind: {kind}")
    if commodity is not None and commodity not in COMMODITY_TERMS:
        raise ValueError(f"unknown commodity: {commodity}")
    if iso not in graph['countries']:
        raise UnknownCountry(f"no data for country: {iso}")
    effects, notes = KINDS[kind](graph, iso, commodity, table)
    effects.sort(key=lambda e: (_ORDER[e['exposure']], -e['driver_percent'], e['name']))
    counts = {level: sum(1 for e in effects if e['exposure'] == level) for level in (HIGH, MODERATE, LOW)}
    return {
        'trigger': {'kind': kind, 'country': iso, 'country_name': graph['countries'][iso]['name'], 'commodity': commodity},
        'effects': effects,
        'counts': counts,
        'notes': notes,
        'method': {
            'trade': f'High from {TRADE_HIGH_PCT:g}% of imports or exports, Moderate from {TRADE_MODERATE_PCT:g}%, Low from {TRADE_LISTED_PCT:g}%.',
            'energy': (f'Importers of the fuel: High when the supplier is at least {TRADE_HIGH_PCT:g}% of imports, or at least {TRADE_MODERATE_PCT:g}% '
                       f'and the country imports {DEPENDENCE_HIGH_PCT:g}% or more of the fuel it uses; Low when it imports under {DEPENDENCE_MODERATE_PCT:g}%.'),
        },
        'not_modelled': NOT_MODELLED,
        'data': {'source': graph.get('source'), 'built_at': graph.get('built_at'), 'countries_in_graph': len(graph['countries'])},
    }


def main():
    parser = argparse.ArgumentParser(description='Run a cascade over the Factbook country graph.')
    parser.add_argument('kind', choices=sorted(KINDS))
    parser.add_argument('country', help='ISO-2 code, for example RU')
    parser.add_argument('--commodity', choices=sorted(COMMODITY_TERMS))
    parser.add_argument('--top', type=int, default=15)
    args = parser.parse_args()
    from services.cascade_graph import get_graph
    result = run(get_graph(), {'kind': args.kind, 'country': args.country, 'commodity': args.commodity}, cascade_trade.load())
    print(json.dumps({**result, 'effects': result['effects'][:args.top]}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
