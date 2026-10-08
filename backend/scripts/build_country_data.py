"""
Builds the bundled country datasets in backend/data/country/ from public files, so the app needs no live call for them:

  hdi.json       Human Development Index by country and year       (UNDP, via Our World in Data, CC BY)
  energy.json    electricity mix and energy use, latest year        (Our World in Data energy data, CC BY)
  minerals.json  production, capacity and reserves by country       (USGS Mineral Commodity Summaries 2025, public domain)

Usage (from backend/):  python scripts/build_country_data.py
Run it again when a new edition is published; each file records its source and year.
"""
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / 'data' / 'country'
CODES_URL = 'https://raw.githubusercontent.com/datasets/country-codes/master/data/country-codes.csv'
HDI_URL = 'https://ourworldindata.org/grapher/human-development-index.csv?useColumnShortNames=true'
ENERGY_URL = 'https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv'
USGS_URL = ('https://www.sciencebase.gov/catalog/file/get/6798fd34d34ea8c18376e8ee?'
            'f=__disk__92%2Ff6%2F90%2F92f690853b1b1dc6a8000c1da24a7bbfd9f670d0')

# Names the USGS file uses that differ from the ISO ones
USGS_ALIASES = {
    'korea, republic of': 'KR', 'korea, north': 'KP', 'korea, south': 'KR', 'burma': 'MM', 'congo (kinshasa)': 'CD', 'congo (brazzaville)': 'CG',
    'russia': 'RU', 'turkey': 'TR', 'türkiye': 'TR', 'turkiye': 'TR', 'czechia': 'CZ', 'czech republic': 'CZ', 'eswatini': 'SZ',
    'swaziland': 'SZ', 'iran': 'IR', 'vietnam': 'VN', 'laos': 'LA', 'taiwan': 'TW', 'bolivia': 'BO', 'venezuela': 'VE', 'tanzania': 'TZ',
    'syria': 'SY', 'moldova': 'MD', 'north macedonia': 'MK', 'macedonia': 'MK', 'brunei': 'BN', 'cabo verde': 'CV', 'cape verde': 'CV',
    'hong kong': 'HK', 'united states': 'US', 'united kingdom': 'GB', 'uae': 'AE', 'united arab emirates': 'AE', "cote d'ivoire": 'CI',
    "côte d'ivoire": 'CI', 'ivory coast': 'CI', 'timor-leste': 'TL', 'east timor': 'TL', 'gabon': 'GA', 'dominican republic': 'DO',
    'democratic republic of the congo': 'CD', 'congo': 'CG', 'palestine': 'PS', 'kyrgyzstan': 'KG', 'slovakia': 'SK', 'serbia': 'RS',
    'kosovo': 'XK', 'myanmar': 'MM', 'the gambia': 'GM', 'gambia': 'GM', 'the bahamas': 'BS', 'bahamas': 'BS',
}

# USGS's own list of critical minerals (2022), matched on the commodity name
CRITICAL = ('aluminum', 'antimony', 'arsenic', 'barite', 'beryllium', 'bismuth', 'cerium', 'cesium', 'chromium', 'chromite', 'cobalt',
            'dysprosium', 'erbium', 'europium', 'fluorspar', 'gadolinium', 'gallium', 'germanium', 'graphite', 'hafnium', 'holmium',
            'indium', 'iridium', 'lanthanum', 'lithium', 'lutetium', 'magnesium', 'manganese', 'platinum', 'palladium', 'neodymium',
            'nickel', 'niobium', 'potash', 'praseodymium', 'rare earths', 'rhodium', 'rubidium', 'ruthenium', 'samarium', 'scandium',
            'tantalum', 'tellurium', 'terbium', 'thulium', 'tin', 'titanium', 'tungsten', 'vanadium', 'ytterbium', 'yttrium', 'zinc',
            'zirconium', 'helium', 'rhenium', 'selenium', 'silicon')


def squash(name):
    """Letters only, lower case: matches a name however its accents, spaces and quotes were written (or damaged)."""
    return re.sub(r'[^a-z]', '', name.lower())


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 GeoIntel'})
    return urllib.request.urlopen(req, timeout=120).read()


def iso_maps():
    rows = list(csv.DictReader(io.StringIO(fetch(CODES_URL).decode('utf-8'))))
    iso3 = {r['ISO3166-1-Alpha-3']: r['ISO3166-1-Alpha-2'] for r in rows if r['ISO3166-1-Alpha-2'] and r['ISO3166-1-Alpha-3']}
    names = {}
    aliases = json.loads((BACKEND / 'data_sources' / 'country_names.json').read_text(encoding='utf-8'))
    for iso2, found in aliases.items():
        for name in found:
            names[squash(name)] = iso2
    for name, iso2 in USGS_ALIASES.items():
        names[squash(name)] = iso2
    return iso3, names


def build_hdi(iso3):
    rows = csv.DictReader(io.StringIO(fetch(HDI_URL).decode('utf-8')))
    out = {}
    for r in rows:
        iso2 = iso3.get(r['code'])
        if iso2 and r.get('hdi__sex_total'):
            out.setdefault(iso2, []).append([int(r['year']), float(r['hdi__sex_total'])])
    for series in out.values():
        series.sort()
    data = {'source': 'UNDP Human Development Report, via Our World in Data', 'license': 'CC BY', 'countries': out}
    (OUT / 'hdi.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    print(f'hdi: {len(out)} countries')


ENERGY_FIELDS = ['coal_share_elec', 'gas_share_elec', 'oil_share_elec', 'nuclear_share_elec', 'hydro_share_elec', 'solar_share_elec',
                 'wind_share_elec', 'biofuel_share_elec', 'other_renewables_share_elec_exc_biofuel', 'fossil_share_elec',
                 'low_carbon_share_elec', 'carbon_intensity_elec', 'electricity_generation', 'energy_per_capita']


def build_energy(iso3):
    rows = csv.DictReader(io.StringIO(fetch(ENERGY_URL).decode('utf-8')))
    best = {}
    for r in rows:
        iso2 = iso3.get(r['iso_code'])
        if not iso2 or not r.get('electricity_generation'):
            continue
        year = int(r['year'])
        if iso2 not in best or year > best[iso2][0]:
            best[iso2] = (year, r)
    out = {}
    for iso2, (year, r) in best.items():
        entry = {'year': year}
        for field in ENERGY_FIELDS:
            try:
                entry[field] = round(float(r[field]), 3)
            except (ValueError, KeyError, TypeError):
                pass
        out[iso2] = entry
    data = {'source': 'Our World in Data energy data (Energy Institute, Ember)', 'license': 'CC BY', 'countries': out}
    (OUT / 'energy.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    print(f'energy: {len(out)} countries')


def number(text):
    text = (text or '').replace(',', '').strip()
    return float(text) if re.fullmatch(r'\d+(?:\.\d+)?', text) else None


def build_minerals(names):
    raw = fetch(USGS_URL).decode('utf-8-sig', errors='replace')
    rows = list(csv.DictReader(io.StringIO(raw)))
    commodities, primary_type, world = {}, {}, {}
    unmatched = set()
    for r in rows:
        commodity = re.sub(r'\s+', ' ', r['COMMODITY'].replace('\xa0', ' ')).strip()
        kind = re.sub(r'\s+', ' ', (r['TYPE'] or '').replace('\xa0', ' ')).strip()
        primary_type.setdefault(commodity, kind)
        if kind != primary_type[commodity]:
            continue
        country = re.sub(r'\s+', ' ', r['COUNTRY'].replace('\xa0', ' ').replace('�', ' ')).strip()
        qualifier = country  # kept for the 'World total' check
        prod_est, prod = number(r['PROD_EST_ 2024']), number(r['PROD_2023'])
        production, year = (prod_est, 2024) if prod_est is not None else (prod, 2023)
        reserves = number(r['RESERVES_2024'])
        capacity = number(r['CAP_EST_ 2024']) if number(r['CAP_EST_ 2024']) is not None else number(r['CAP_2023'])
        if qualifier.lower().startswith('world total'):
            world[commodity] = {'production': production, 'year': year, 'reserves': reserves}
            continue
        # 'Congo (Kinshasa)' is a name; '(andalusite)' is a note on the name before it: try the whole text first
        iso2 = names.get(squash(country)) or names.get(squash(re.sub(r'\s*\(.*\)\s*$', '', country)))
        if not iso2:
            unmatched.add(country)
            continue
        if production is None and reserves is None and capacity is None:
            continue
        commodities.setdefault(commodity, []).append({
            'country': iso2, 'production': production, 'year': year if production is not None else None, 'capacity': capacity,
            'reserves': reserves, 'unit': (r['UNIT_MEAS'] or '').strip(), 'type': kind})
    out = {}
    for commodity, entries in commodities.items():
        total = (world.get(commodity) or {}).get('production') or sum(e['production'] or 0 for e in entries)
        res_total = (world.get(commodity) or {}).get('reserves') or sum(e['reserves'] or 0 for e in entries)
        ranked = sorted([e for e in entries if e['production']], key=lambda e: -e['production'])
        rank_by = {e['country']: i + 1 for i, e in enumerate(ranked)}
        for e in entries:
            row = {'commodity': commodity, 'critical': any(c in commodity.lower() for c in CRITICAL), 'unit': e['unit'], 'type': e['type']}
            if e['production']:
                row.update(production=e['production'], year=e['year'], rank=rank_by[e['country']], producers=len(ranked),
                           world_share=round(e['production'] / total * 100, 1) if total else None)
            if e['capacity']:
                row['capacity'] = e['capacity']
            if e['reserves']:
                row.update(reserves=e['reserves'], reserves_share=round(e['reserves'] / res_total * 100, 1) if res_total else None)
            out.setdefault(e['country'], []).append(row)
    data = {'source': 'USGS Mineral Commodity Summaries 2025', 'license': 'public domain', 'countries': out}
    (OUT / 'minerals.json').write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    print(f'minerals: {len(out)} countries, {len(commodities)} commodities; unmatched names: {sorted(unmatched)}')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    iso3, names = iso_maps()
    build_hdi(iso3)
    build_energy(iso3)
    build_minerals(names)


if __name__ == '__main__':
    sys.exit(main())
