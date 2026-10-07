"""Build backend/data_sources/migration_origins.json from the UN DESA International Migrant Stock 2024 workbook
(Table 1, both sexes, 2024 column) and the factbook folder codes from the datasets/country-codes list.

Usage: python scripts/build_migration_data.py <path to undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx>
The workbook is public: un.org/development/desa/pd (International Migrant Stock 2024). Output: for each destination
country (ISO alpha-2) the migrant stock and its top origin countries, so the app needs no live call.
"""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

import openpyxl

TOP = 15
YEAR_COL = 14  # zero-based column of the 2024 value in the first (both sexes) block
CODES_URL = 'https://raw.githubusercontent.com/datasets/country-codes/master/data/country-codes.csv'


def main(path):
    raw = urllib.request.urlopen(CODES_URL).read().decode('utf-8')
    m49_to_iso = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row['M49'] and row['ISO3166-1-Alpha-2']:
            m49_to_iso[int(row['M49'])] = row['ISO3166-1-Alpha-2']

    ws = openpyxl.load_workbook(path, read_only=True)['Table 1']
    out = {}
    for r in ws.iter_rows(min_row=12, values_only=True):
        dest, origin, value = m49_to_iso.get(r[4]), m49_to_iso.get(r[6]), r[YEAR_COL]
        if not dest or not origin or not isinstance(value, (int, float)) or value <= 0:
            continue
        entry = out.setdefault(dest, {'total': 0, 'origins': []})
        entry['total'] += int(value)
        entry['origins'].append([origin, int(value)])
    for entry in out.values():
        entry['origins'].sort(key=lambda o: -o[1])
        entry['origins'] = entry['origins'][:TOP]
    target = Path(__file__).resolve().parent.parent / 'data_sources' / 'migration_origins.json'
    target.write_text(json.dumps({'year': 2024, 'source': 'UN DESA International Migrant Stock 2024', 'countries': out},
                                 separators=(',', ':'), sort_keys=True), encoding='utf-8')
    print(f'{len(out)} destination countries -> {target}')


if __name__ == '__main__':
    main(sys.argv[1])
