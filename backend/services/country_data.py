"""
The bundled country datasets (backend/data/country/*.json, built by scripts/build_country_data.py): Human Development Index,
electricity mix and minerals. Each loader returns None for a country the dataset does not cover, and every result names its
source and year. Nothing is fetched at request time.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'country'

HDI_TIERS = ((0.800, 'Very high'), (0.700, 'High'), (0.550, 'Medium'), (0.0, 'Low'))


@lru_cache(maxsize=8)
def _load(name):
    path = DATA_DIR / f'{name}.json'
    if not path.exists():
        return {'countries': {}}
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _hdi_latest():
    return {cc: series[-1] for cc, series in _load('hdi')['countries'].items() if series}


def hdi(cc):
    """{'value', 'year', 'tier', 'rank', 'of', 'series', 'source'} for the Human Development Index (1 is the highest value)."""
    series = _load('hdi')['countries'].get(cc)
    if not series:
        return None
    year, value = series[-1]
    latest = _hdi_latest()
    higher = sum(1 for _, v in latest.values() if v > value)
    tier = next(name for floor, name in HDI_TIERS if value >= floor)
    return {'value': value, 'year': year, 'tier': tier, 'rank': higher + 1, 'of': len(latest), 'series': series,
            'source': _load('hdi').get('source')}


_MIX = (('nuclear_share_elec', 'Nuclear'), ('coal_share_elec', 'Coal'), ('gas_share_elec', 'Gas'), ('oil_share_elec', 'Oil'),
        ('hydro_share_elec', 'Hydro'), ('wind_share_elec', 'Wind'), ('solar_share_elec', 'Solar'),
        ('biofuel_share_elec', 'Bioenergy'), ('other_renewables_share_elec_exc_biofuel', 'Other renewables'))


def energy(cc):
    """Where the country's electricity comes from (share of generation, latest year), plus totals and carbon intensity."""
    row = _load('energy')['countries'].get(cc)
    if not row:
        return None
    mix = [{'name': label, 'percent': row[field]} for field, label in _MIX if row.get(field)]
    mix.sort(key=lambda m: -m['percent'])
    return {
        'year': row['year'], 'mix': mix, 'fossil_share': row.get('fossil_share_elec'), 'low_carbon_share': row.get('low_carbon_share_elec'),
        'carbon_intensity': row.get('carbon_intensity_elec'), 'generation_twh': row.get('electricity_generation'),
        'energy_per_capita_kwh': row.get('energy_per_capita'), 'source': _load('energy').get('source'),
    }


def minerals(cc):
    """What the country mines and holds (USGS): critical minerals first, then by share of world production, then reserves."""
    rows = _load('minerals')['countries'].get(cc)
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: (not r['critical'], -(r.get('world_share') or 0), -(r.get('reserves_share') or 0), r['commodity']))
    return {'items': ordered, 'source': _load('minerals').get('source')}
