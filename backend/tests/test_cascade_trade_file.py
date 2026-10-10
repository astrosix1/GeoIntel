"""The bundled commodity trade table (backend/data/cascade/trade.json), when it has been built: its shape, its limits and its licence note.
Skipped until the file exists, so the suite passes before and after the build."""
import json

import pytest

from services import cascade_trade

TABLE = cascade_trade.load()
pytestmark = pytest.mark.skipif(TABLE is None, reason='the trade table has not been built yet')

MAX_RECORDS = 100_000          # the UN Comtrade re-dissemination policy's threshold for "a limited amount"


def test_every_group_the_engine_asks_for_exists_in_the_table():
    wanted = {g for groups in cascade_trade.GROUPS.values() for g in groups}
    assert wanted <= set(TABLE['commodities'])


def test_entries_are_well_formed_shares_of_a_positive_total():
    for iso, groups in TABLE['imports'].items():
        assert len(iso) == 2 and iso.isupper()
        for group, entry in groups.items():
            assert group in TABLE['commodities']
            assert entry['total'] > 0 and entry['year'] in (2021, 2022, 2023)
            shares = entry['shares']
            assert len(shares) <= 12 and all(len(k) == 2 and 0 < v <= 100 for k, v in shares.items())
            assert sum(shares.values()) <= 100.5, f'{iso} {group} shares add to more than the whole'


def test_stays_under_the_licence_threshold_and_names_its_source():
    records = sum(len(e['shares']) + 1 for groups in TABLE['imports'].values() for e in groups.values())
    assert records < MAX_RECORDS
    assert 'UN Comtrade' in TABLE['source'] and 'transformed' in TABLE['license']


def test_the_file_holds_shares_not_raw_values():
    text = json.dumps(TABLE)
    assert '"partners"' not in text                       # the old raw-value key must not appear


def test_known_facts_hold_when_the_countries_are_present():
    egypt = TABLE['imports'].get('EG', {}).get('cereals')
    if egypt:
        assert egypt['shares'].get('RU', 0) > 10          # Egypt buys a large part of its grain from Russia
