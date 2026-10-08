"""Migration tab: UN DESA trends and emigration (bundled), UNHCR (mocked), remittances (mocked)."""
from unittest.mock import patch

import pytest

from data_sources import unhcr
from services import country_migration as cm
from services import country_tabs as ct


@pytest.fixture(autouse=True)
def no_cache():
    with patch('data_sources.unhcr.cache_get', return_value=None), patch('data_sources.unhcr.cache_set'), \
         patch('services.country_tabs.cache_get', return_value=None), patch('services.country_tabs.cache_set'):
        yield


COUNTRIES = [
    {'iso2': 'DE', 'iso': 'DEU', 'code': 'GFR'}, {'iso2': 'SY', 'iso': 'SYR', 'code': 'SYR'}, {'iso2': 'DZ', 'iso': 'DZA', 'code': 'ALG'},
]


class TestUnhcr:
    def _fake(self, calls):
        def fake(path, params):
            calls.append((path, params))
            if path == 'countries/':
                return COUNTRIES
            if params.get('coa_all') or params.get('coo_all'):
                return [
                    {'coo_iso': 'SYR', 'coa_iso': 'DEU', 'refugees': 700, 'asylum_seekers': 50},
                    {'coo_iso': 'DZA', 'coa_iso': 'DEU', 'refugees': 10},
                    {'coo_iso': 'XXX', 'coa_iso': 'DEU', 'refugees': 999},       # unknown country: left out
                    {'coo_iso': 'SYR', 'coa_iso': 'DEU'},                         # nothing counted: left out
                ]
            return [{'year': 2024, 'refugees': 5, 'asylum_seekers': 0, 'stateless': 3}, {'year': 2023, 'refugees': 4}]
        return fake

    def test_the_api_is_asked_with_unhcr_codes_not_iso(self):
        calls = []
        with patch('data_sources.unhcr._items', side_effect=self._fake(calls)):
            unhcr.hosted_series('DE')
        assert calls[-1][1]['coa'] == 'GFR'

    def test_series_is_oldest_first_and_leaves_out_zero_fields(self):
        with patch('data_sources.unhcr._items', side_effect=self._fake([])):
            rows = unhcr.hosted_series('DE')
        assert [r['year'] for r in rows] == [2023, 2024]
        assert rows[1] == {'year': 2024, 'refugees': 5, 'stateless': 3}

    def test_breakdown_translates_partners_to_iso2_and_sorts(self):
        with patch('data_sources.unhcr._items', side_effect=self._fake([])):
            rows = unhcr.hosted_by_origin('DE', 2024)
        assert [(r['country_code'], r['total']) for r in rows] == [('SY', 750), ('DZ', 10)]

    def test_unknown_country_or_failure_is_none(self):
        with patch('data_sources.unhcr._items', side_effect=self._fake([])):
            assert unhcr.hosted_series('ZZ') is None
        with patch('data_sources.unhcr._items', return_value=None):
            assert unhcr.hosted_series('DE') is None
            assert unhcr.hosted_by_origin('DE', 2024) is None


class TestUn:
    def test_immigrant_trend_share_and_origins(self):
        population = {1990: 56_000_000, 2005: 63_000_000, 2020: 67_000_000, 2024: 68_000_000}
        immigrants, emigrants = cm.build_un('FR', population)
        assert immigrants['stock'] == 9186757 and immigrants['series'][0][0] == 1990
        assert immigrants['origins'][0]['country_code'] == 'DZ'
        assert immigrants['share_of_population'] == round(9186757 / 68_000_000 * 100, 1)
        assert immigrants['share_series'][0] == [1990, round(5890023 / 56_000_000 * 100, 2)]
        assert immigrants['other_count'] > 0

    def test_emigrants_are_the_same_table_read_from_the_other_side(self):
        _, emigrants = cm.build_un('SY', {2024: 24_000_000})
        assert emigrants['destinations'][0]['country_code'] == 'TR'
        assert emigrants['stock'] > 5_000_000 and emigrants['share_of_population'] > 20

    def test_a_country_not_in_the_table_has_nothing(self):
        assert cm.build_un('ZZ', {}) == (None, None)


class TestTab:
    @patch('services.country_migration.unhcr')
    @patch('services.country_migration.wb')
    def test_groups_are_left_out_when_their_source_has_nothing(self, wbmod, unh):
        wbmod.series.return_value = [[2024, 68_000_000]]
        wbmod.stats.return_value = []
        unh.hosted_series.return_value = unh.origin_series.return_value = None
        out = cm.build_tab('FR')
        assert 'immigrants' in out and 'emigrants' in out
        assert 'refugees' not in out and 'stats' not in out
        assert out['sources'] == ['UN DESA International Migrant Stock 2024']

    @patch('services.country_migration.unhcr')
    @patch('services.country_migration.wb')
    def test_unhcr_groups_use_the_latest_year_of_each_series(self, wbmod, unh):
        wbmod.series.return_value = [[2024, 68_000_000]]
        wbmod.stats.return_value = []
        unh.SOURCE = 'UNHCR Refugee Statistics'
        unh.hosted_series.return_value = [{'year': 2024, 'refugees': 5}, {'year': 2025, 'refugees': 6}]
        unh.origin_series.return_value = [{'year': 2025, 'refugees': 9, 'idps': 3}]
        unh.hosted_by_origin.return_value = [{'country_code': 'SY', 'total': 6}]
        unh.abroad_by_destination.return_value = None
        out = cm.build_tab('FR')
        unh.hosted_by_origin.assert_called_once_with('FR', 2025)
        assert out['refugees']['hosted']['latest']['refugees'] == 6
        assert out['refugees']['from_here']['by_destination'] is None

    @patch('services.country_migration.unhcr')
    @patch('services.country_migration.wb')
    def test_nothing_anywhere_is_none(self, wbmod, unh):
        wbmod.series.return_value = None
        wbmod.stats.return_value = []
        unh.hosted_series.return_value = unh.origin_series.return_value = None
        assert cm.build_tab('ZZ') is None

    @patch('services.country_tabs.FactbookConnector')
    @patch('services.country_tabs.bundled')
    def test_the_tab_adds_the_factbook_net_migration_rate(self, bundled, fb):
        fb.fetch_profile.return_value = {'people': {'net_migration_rate': {'value': 1.06, 'as_of': 2025}}}
        with patch('services.country_migration.build_tab', return_value={'country_code': 'FR', 'tab': 'migration', 'sources': []}):
            out = ct.get_country_tab('FR', 'migration')
        assert out['net_migration_rate']['value'] == 1.06 and 'CIA World Factbook' in out['sources']
