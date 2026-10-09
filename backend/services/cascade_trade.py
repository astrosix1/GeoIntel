"""The commodity-level trade table the cascade engine prefers over the Factbook's all-goods partner lists: for each country and
commodity group, its imports (total value, newest year available) and each top supplier's share. Bundled in
backend/data/cascade/trade.json by scripts/build_cascade_trade.py from the UN Comtrade public preview API; nothing is fetched at
request time. Returns None for everything when the file has not been built, and the engine falls back to the Factbook.
"""
import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / 'data' / 'cascade' / 'trade.json'

# What a trigger's commodity means in the table (one trigger commodity can span several groups).
GROUPS = {
    'gas': ('gas',),
    'oil': ('crude_oil', 'oil_products'),
    'coal': ('coal',),
    'grain': ('cereals',),
    'veg_oils': ('veg_oils',),
    'fertilizers': ('fertilizers',),
    'iron_ore': ('iron_ore',),
    'copper': ('copper',),
    'aluminium': ('aluminium',),
    'chips': ('chips',),
}


@lru_cache(maxsize=1)
def load():
    """The table, or None when it has not been built."""
    try:
        return json.loads(PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def combined(table, importer, commodity):
    """{'total', 'year', 'shares': {iso: percent}} for one importer and one trigger commodity, merging its groups (shares are weighted
    by each group's import value). None when the importer has no data for it."""
    groups = [(table['imports'].get(importer) or {}).get(g) for g in GROUPS.get(commodity, ())]
    groups = [g for g in groups if g and g.get('total')]
    if not groups:
        return None
    total = sum(g['total'] for g in groups)
    shares = {}
    for g in groups:
        for iso, percent in g['shares'].items():
            shares[iso] = shares.get(iso, 0.0) + percent * g['total'] / total
    return {'total': total, 'year': max(g['year'] for g in groups), 'shares': {k: round(v, 1) for k, v in shares.items()}}
