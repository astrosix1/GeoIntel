"""Build backend/data_sources/migration_origins.json from the UN DESA International Migrant Stock 2024 workbook
(Table 1, both sexes, 2024 column) and the factbook folder codes from the datasets/country-codes list.

Usage: python scripts/build_migration_data.py <path to undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx>
The workbook is public: un.org/development/desa/pd (International Migrant Stock 2024). Output: for each destination
country (ISO alpha-2) the migrant stock and its top origin countries, so the app needs no live call.
"""
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import openpyxl

TOP = 15
YEAR_COL = 14  # zero-based column of the 2024 value in the first (both sexes) block
CODES_URL = 'https://raw.githubusercontent.com/datasets/country-codes/master/data/country-codes.csv'


# The names the news feed (GDELT) uses where they differ from the ISO ones.
ALIASES = {'US': ['United States'], 'GB': ['United Kingdom'], 'TR': ['Turkey'], 'SK': ['Slovak Republic'], 'CZ': ['Czech Republic'],
           'MK': ['Macedonia'], 'RS': ['Serbia (general)'], 'PS': ['West Bank', 'Gaza Strip'], 'RE': ['Reunion'], 'CD': ['Democratic Republic of Congo'],
           'CG': ['Congo']}


def write_names(rows):
    """country_names.json: ISO alpha-2 -> every name a country is known by in the events table."""
    names = {}
    for row in rows:
        iso = row['ISO3166-1-Alpha-2']
        if not iso:
            continue
        found = {row.get(c, '').strip() for c in ('CLDR display name', 'UNTERM English Short', 'official_name_en') if row.get(c, '').strip()}
        found = {re.sub(r'^the ', '', n.replace(' (the)', ''), flags=re.I) for n in found} | set(ALIASES.get(iso, []))
        names[iso] = sorted(found)
    target = Path(__file__).resolve().parent.parent / 'data_sources' / 'country_names.json'
    target.write_text(json.dumps(names, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')


YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2024]  # the table's years, in column order (both sexes block starts at column 7)
WORLD = 900  # the table's own code for "all origins" / "all destinations"


def main(path):
    raw = urllib.request.urlopen(CODES_URL).read().decode('utf-8')
    rows = list(csv.DictReader(io.StringIO(raw)))
    write_names(rows)
    m49_to_iso = {}
    iso2_to_iso3 = {}
    for row in rows:
        if row['M49'] and row['ISO3166-1-Alpha-2']:
            m49_to_iso[int(row['M49'])] = row['ISO3166-1-Alpha-2']
        if row['ISO3166-1-Alpha-2'] and row['ISO3166-1-Alpha-3']:
            iso2_to_iso3[row['ISO3166-1-Alpha-2']] = row['ISO3166-1-Alpha-3']
    (Path(__file__).resolve().parent.parent / 'data_sources' / 'country_iso3.json').write_text(
        json.dumps(iso2_to_iso3, separators=(',', ':'), sort_keys=True), encoding='utf-8')

    ws = openpyxl.load_workbook(path, read_only=True)['Table 1']
    out = {}

    def entry(code):
        return out.setdefault(code, {'total': 0, 'origins': [], 'series': [], 'emigrants': {'total': 0, 'destinations': [], 'series': []}})

    for r in ws.iter_rows(min_row=12, values_only=True):
        values = list(r[7:7 + len(YEAR_LABELS_COUNT)])
        dest = m49_to_iso.get(r[4]) if r[4] != WORLD else WORLD
        origin = m49_to_iso.get(r[6]) if r[6] != WORLD else WORLD
        if dest is None or origin is None or (dest == WORLD and origin == WORLD):
            continue
        if not isinstance(values[-1], (int, float)) and not any(isinstance(v, (int, float)) for v in values):
            continue
        series = [[y, int(v)] for y, v in zip(YEARS, values) if isinstance(v, (int, float))]
        latest = values[-1] if isinstance(values[-1], (int, float)) else 0
        if origin == WORLD:      # everyone living in `dest` who was born elsewhere
            entry(dest)['series'] = series
            continue
        if dest == WORLD:        # everyone born in `origin` who lives elsewhere
            entry(origin)['emigrants']['series'] = series
            continue
        if latest and latest > 0:
            e = entry(dest)
            e['total'] += int(latest)
            e['origins'].append([origin, int(latest)])
            em = entry(origin)['emigrants']
            em['total'] += int(latest)
            em['destinations'].append([dest, int(latest)])
    for e in out.values():
        e['origins'].sort(key=lambda o: -o[1])
        e['origins'] = e['origins'][:TOP]
        e['emigrants']['destinations'].sort(key=lambda o: -o[1])
        e['emigrants']['destinations'] = e['emigrants']['destinations'][:TOP]
    target = Path(__file__).resolve().parent.parent / 'data_sources' / 'migration_origins.json'
    target.write_text(json.dumps({'year': 2024, 'years': YEARS, 'source': 'UN DESA International Migrant Stock 2024', 'countries': out},
                                 separators=(',', ':'), sort_keys=True), encoding='utf-8')
    print(f'{len(out)} countries -> {target}')


YEAR_LABELS_COUNT = YEARS


if __name__ == '__main__':
    main(sys.argv[1])
