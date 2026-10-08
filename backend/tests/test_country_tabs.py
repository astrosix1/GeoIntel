"""Per-tab country data and the World Bank indicator helper. Network connectors are mocked."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from blueprints.countries import countries_bp
from data_sources.factbook import parse_profile
from services import country_indicators as ci
from services import country_tabs as ct

FIX = Path(__file__).parent / 'fixtures' / 'factbook'
FR = parse_profile(json.loads((FIX / 'fr.json').read_text(encoding='utf-8')))


def _row(code, value, year):
    return {'country': {'id': code}, 'value': value, 'date': str(year)}


@pytest.fixture(autouse=True)
def no_cache():
    with patch('services.country_indicators.cache_get', return_value=None), patch('services.country_indicators.cache_set'), \
         patch('services.country_tabs.cache_get', return_value=None), patch('services.country_tabs.cache_set'):
        yield


class TestIndicators:
    def test_series_is_oldest_first_and_drops_empty_years(self):
        body = [{}, [_row('FR', 70.5, 2022), _row('FR', None, 2023), _row('FR', 69.0, 2021)]]
        with patch('services.country_indicators._get', return_value=body):
            assert ci.series('FR', 'X') == [[2021, 69.0], [2022, 70.5]]

    def test_series_is_none_when_nothing_comes_back(self):
        with patch('services.country_indicators._get', return_value=None):
            assert ci.series('FR', 'X') is None
        with patch('services.country_indicators._get', return_value=[{}, []]):
            assert ci.series('FR', 'X') is None

    def test_rank_counts_only_the_table_and_one_is_highest(self):
        table = {'FR': [10, 2024], 'DE': [30, 2024], 'ES': [20, 2024]}
        with patch('services.country_indicators.latest_all', return_value=table):
            assert ci.rank_of('FR', 'X') == (3, 3)
            assert ci.rank_of('DE', 'X') == (1, 3)
            assert ci.rank_of('ZZ', 'X') is None

    def test_latest_all_leaves_out_aggregates_and_empty_values(self):
        body = [{}, [_row('FR', 5, 2024), _row('1W', 9, 2024), _row('DE', None, 2024)]]
        with patch('services.country_indicators._get', return_value=body), \
             patch('services.country_indicators.real_countries', return_value={'FR', 'DE'}):
            assert ci.latest_all('X') == {'FR': [5, 2024]}

    def test_stat_carries_value_year_series_and_rank(self):
        with patch('services.country_indicators.series', return_value=[[2023, 1.0], [2024, 2.0]]), \
             patch('services.country_indicators.rank_of', return_value=(5, 200)):
            out = ci.stat('FR', 'X', 'Label', 'units', 2)
        assert (out['value'], out['year'], out['rank'], out['of'], out['source']) == (2.0, 2024, 5, 200, 'World Bank')
        assert out['series'] == [[2023, 1.0], [2024, 2.0]]

    def test_stats_skips_the_missing_ones_and_keeps_order(self):
        def fake(cc, code, label, *a):
            return None if code == 'B' else {'code': code, 'label': label}
        with patch('services.country_indicators.stat', side_effect=fake):
            assert [s['code'] for s in ci.stats('FR', [('A', 'a'), ('B', 'b'), ('C', 'c')])] == ['A', 'C']


class TestTabs:
    def test_unknown_tab_or_country(self):
        assert ct.get_country_tab('FR', 'nonsense') is None
        assert ct.get_country_tab('', 'people') is None

    @patch('services.country_tabs.FactbookConnector')
    def test_government_tab_carries_only_government(self, fb):
        fb.fetch_profile.return_value = FR
        out = ct.get_country_tab('fr', 'government')
        assert out['tab'] == 'government' and out['government']['type'] == 'semi-presidential republic'
        assert 'people' not in out and 'economy' not in out and out['sources'] == ['CIA World Factbook']

    @patch('services.country_tabs.wb')
    @patch('services.country_tabs.FactbookConnector')
    def test_people_tab_has_estimated_counts_and_stats(self, fb, wbmod):
        fb.fetch_profile.return_value = FR
        wbmod.stats.return_value = [{'code': 'SP.POP.TOTL', 'label': 'Population', 'value': 68000000, 'year': 2024}]
        wbmod.SOURCE = 'World Bank'
        out = ct.get_country_tab('FR', 'people')
        assert out['population'] == 68000000 and out['stats'][0]['label'] == 'Population'
        assert out['people']['religions']['items'][0]['estimated_count'] == round(68000000 * 0.47)

    @patch('services.country_tabs.build_conflicts', return_value=None)
    @patch('services.country_tabs.bundled')
    @patch('services.country_tabs.wb')
    @patch('services.country_tabs.FactbookConnector')
    def test_nothing_real_is_none(self, fb, wbmod, bundled, _conflicts):
        fb.fetch_profile.return_value = None
        wbmod.stats.return_value = []
        bundled.energy.return_value = bundled.minerals.return_value = bundled.hdi.return_value = None
        assert ct.get_country_tab('FR', 'government') is None
        assert ct.get_country_tab('FR', 'economy') is None
        with patch('services.country_security.build_tab', return_value=None):
            assert ct.get_country_tab('FR', 'security') is None

    @patch('services.country_security.build_tab', return_value={'country_code': 'FR', 'tab': 'security', 'sources': ['CIA World Factbook']})
    @patch('services.country_tabs.build_conflicts')
    def test_security_tab_adds_fresh_conflicts(self, conflicts, _tab):
        conflicts.return_value = {'total': 3, 'source': 'GeoIntel events (GDELT news feed)'}
        out = ct.get_country_tab('FR', 'security')
        assert out['conflicts']['total'] == 3 and 'GeoIntel events (GDELT news feed)' in out['sources']

    def test_geography_tab_exists_even_before_it_has_data(self):
        assert ct.get_country_tab('FR', 'geography')['tab'] == 'geography'


def test_endpoint_is_premium_only():
    app = Flask(__name__)
    app.register_blueprint(countries_bp)
    with app.test_client() as c:
        assert c.get('/api/countries/FR/tab/people').status_code == 401


class TestNewFigures:
    @patch('services.country_tabs.FactbookConnector')
    @patch('services.country_tabs.wb')
    def test_people_tab_carries_hdi_and_more_figures(self, wbmod, fb):
        fb.fetch_profile.return_value = FR
        wbmod.stats.return_value = [{'code': 'SP.POP.TOTL', 'label': 'Population', 'value': 68000000, 'year': 2024}]
        wbmod.SOURCE = 'World Bank'
        out = ct.get_country_tab('FR', 'people')
        assert out['hdi']['value'] > 0.9 and out['hdi']['tier'] == 'Very high'
        assert any('UNDP' in s for s in out['sources'])
        assert wbmod.stats.call_args[0][1] is ct.PEOPLE_STATS

    @patch('services.country_tabs.FactbookConnector')
    @patch('services.country_tabs.wb')
    def test_economy_tab_carries_energy_minerals_and_sectors(self, wbmod, fb):
        fb.fetch_profile.return_value = FR
        wbmod.stats.return_value = []
        wbmod.SOURCE = 'World Bank'
        out = ct.get_country_tab('FR', 'economy')
        assert out['energy']['mix'][0]['name'] == 'Nuclear'
        assert out['minerals']['items'] and out['sectors'] == []
        assert out['economy']['exports']['items'][0] == 'aircraft'
