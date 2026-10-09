"""The cascade graph and engine: rules row by row against small fixture graphs (no network)."""
import json

import pytest

from data_sources.factbook import parse_energy_fuels, parse_quantity
from services import cascade_engine as ce
from services.cascade_graph import build_graph, country_name, partner_iso


def partners(*pairs, as_of=2023):
    return {'items': [{'name': n, 'percent': p, 'under': False} for n, p in pairs], 'as_of': as_of}


def profile(exports=None, imports=None, commodities=None, fuels=None):
    return {'economy': {'export_partners': exports, 'import_partners': imports,
                        'exports': {'items': commodities or [], 'as_of': 2023} if commodities else None}, 'energy_fuels': fuels or {}}


def gas(production, consumption, imports=None):
    out = {'production': {'value': production, 'unit': 'm3', 'as_of': 2023}, 'consumption': {'value': consumption, 'unit': 'm3', 'as_of': 2023}}
    if imports is not None:
        out['imports'] = {'value': imports, 'unit': 'm3', 'as_of': 2023}
    return {'gas': out}


@pytest.fixture()
def graph():
    return build_graph({
        'RU': profile(exports=partners(('China', 33), ('India', 17), ('Turkey', 6), ('Germany', 1)), commodities=['petroleum', 'natural gas', 'wheat'],
                      fuels=gas(600e9, 470e9)),
        'DE': profile(imports=partners(('Russia', 5), ('China', 12)), fuels=gas(4e9, 82e9, 75e9)),
        'TR': profile(imports=partners(('Russia', 9)), fuels=gas(0.4e9, 50e9, 50e9)),
        'IN': profile(imports=partners(('Russia', 10)), fuels=gas(30e9, 60e9, 29e9)),
        'NO': profile(imports=partners(('Russia', 20)), fuels=gas(120e9, 5e9)),       # supplies itself: Low at most
        'BG': profile(imports=partners(('Russia', 3))),                                # no fuel balance published
        'CN': profile(imports=partners(('Russia', 4))),
        'XX': profile(imports=partners(('Russia', 1))),                                # negligible share
        'FR': None,
    })


class TestHelpers:
    def test_parse_quantity(self):
        assert parse_quantity('4.337 billion cubic meters (2023 est.)') == {'value': 4.337e9, 'unit': 'm3', 'as_of': 2023}
        assert parse_quantity('10.879 million bbl/day (2023 est.)')['value'] == pytest.approx(10.879e6)
        assert parse_quantity('131,000 bbl/day (2023 est.)')['value'] == 131000
        assert parse_quantity('nothing here') is None and parse_quantity(None) is None

    def test_parse_energy_fuels(self):
        data = {'Energy': {'Natural gas': {'production': {'text': '4 billion cubic meters (2023 est.)'}, 'consumption': {'text': '8 billion cubic meters (2023 est.)'}},
                           'Petroleum': {'total petroleum production': {'text': '1.5 million bbl/day (2023 est.)'}}}}
        fuels = parse_energy_fuels(data)
        assert fuels['gas']['consumption']['value'] == 8e9 and fuels['oil']['production']['value'] == 1.5e6
        assert parse_energy_fuels({}) == {}

    def test_partner_names_map_to_countries(self):
        assert partner_iso('USA') == 'US' and partner_iso('Korea, South') == 'KR' and partner_iso('Czechia') == 'CZ'
        assert partner_iso('Nowhereland') is None and country_name('GB') == 'United Kingdom'

    def test_graph_drops_empty_profiles_and_reports_unmapped_names(self):
        g = build_graph({'AA': profile(imports=partners(('Nowhereland', 5))), 'BB': None})
        assert 'BB' not in g['countries'] and g['unmapped_partner_names'] == ['Nowhereland']
        assert list(build_graph({'AA': profile(imports=partners(('Russia', 5)))}, allowed=set())['countries']) == []


class TestTrade:
    @pytest.mark.parametrize('percent,level', [(60, 'High'), (15, 'High'), (14.9, 'Moderate'), (5, 'Moderate'), (4.9, 'Low'), (2, 'Low'), (1.9, None)])
    def test_thresholds(self, percent, level):
        assert ce.trade_level(percent) == level

    def test_supply_loss_ranks_buyers_by_share_with_evidence(self, graph):
        result = ce.run(graph, {'kind': 'supply_loss', 'country': 'RU'})
        by = {e['iso']: e for e in result['effects']}
        assert by['NO']['exposure'] == 'High' and by['NO']['driver_percent'] == 20
        assert by['IN']['exposure'] == 'Moderate' and by['CN']['exposure'] == 'Low'
        assert 'XX' not in by                                                   # 1% is negligible
        first = by['NO']['evidence'][0]
        assert first['text'] == "Russia supplies 20% of Norway's imports." and first['source'] == 'CIA World Factbook' and first['as_of'] == 2023
        assert [e['iso'] for e in result['effects']][0] == 'NO'

    def test_demand_loss_looks_at_the_sellers(self, graph):
        result = ce.run(graph, {'kind': 'demand_loss', 'country': 'CN'})
        assert [(e['iso'], e['exposure']) for e in result['effects']] == [('RU', 'High')]
        assert result['effects'][0]['evidence'][0]['text'] == "China takes 33% of Russia's exports."


class TestEnergy:
    def test_dependence(self):
        dep = ce.fuel_dependence(gas(4e9, 82e9, 75e9), 'gas')
        assert dep['percent'] == pytest.approx(91.46, abs=0.01) and 'imports' in dep['text']
        assert ce.fuel_dependence(gas(30e9, 60e9), 'gas')['percent'] == 50.0          # from production when imports are not published
        assert ce.fuel_dependence(gas(100e9, 60e9), 'gas')['percent'] == 0.0
        assert ce.fuel_dependence({}, 'gas') is None and ce.fuel_dependence(None, 'oil') is None

    def test_supplier_check(self):
        assert ce.supplies({'export_commodities': ['crude oil']}, 'oil')[0]
        assert ce.supplies({'fuels': gas(200e9, 100e9)}, 'gas')[0]
        assert not ce.supplies({'fuels': gas(100e9, 100e9)}, 'gas')[0]
        assert not ce.supplies({'export_commodities': ['cars']}, 'gas')[0]

    def test_russian_gas_embargo(self, graph):
        result = ce.run(graph, {'kind': 'supply_loss', 'country': 'RU', 'commodity': 'gas'})
        by = {e['iso']: e for e in result['effects']}
        assert by['TR']['exposure'] == 'High'                       # 9% supplier, imports 100% of its gas
        assert by['DE']['exposure'] == 'High'                       # 5% supplier, imports 91% of its gas
        assert by['IN']['exposure'] == 'Moderate'                   # 10% supplier, imports 48%
        assert by['NO']['exposure'] == 'Low'                        # imports under 20%: it supplies itself
        assert by['BG']['exposure'] == 'Low' and any('no natural gas balance' in c for c in by['BG']['caveats'])
        assert any('imports about' in e['text'] for e in by['TR']['evidence'][1:])
        assert all(e['horizon'] == 'days to weeks' for e in result['effects'])

    def test_a_commodity_the_country_does_not_supply_lists_nothing(self, graph):
        result = ce.run(graph, {'kind': 'supply_loss', 'country': 'DE', 'commodity': 'grain'})
        assert result['effects'] == [] and 'not shown to export grain' in result['notes'][0]

    def test_commodity_without_volumes_is_capped_at_moderate(self, graph):
        result = ce.run(graph, {'kind': 'supply_loss', 'country': 'RU', 'commodity': 'grain'})
        by = {e['iso']: e for e in result['effects']}
        assert by['NO']['exposure'] == 'Moderate' and any('capped at Moderate' in c for c in by['NO']['caveats'])
        assert by['NO']['horizon'] == 'weeks to months'


class TestRun:
    def test_deterministic_and_complete_output(self, graph):
        trigger = {'kind': 'supply_loss', 'country': 'ru', 'commodity': 'gas'}
        a, b = ce.run(graph, trigger), ce.run(graph, trigger)
        assert a == b
        assert a['trigger']['country'] == 'RU' and a['counts']['High'] + a['counts']['Moderate'] + a['counts']['Low'] == len(a['effects'])
        assert a['not_modelled'] and a['method']['trade'] and a['data']['countries_in_graph'] == len(graph['countries'])

    def test_no_probability_or_percent_chance_anywhere(self, graph):
        text = json.dumps(ce.run(graph, {'kind': 'supply_loss', 'country': 'RU', 'commodity': 'gas'})).lower()
        assert 'probab' not in text and 'chance' not in text and 'likelihood' not in text

    def test_bad_input(self, graph):
        for trigger, error in (({'kind': 'nope', 'country': 'RU'}, ValueError), ({'kind': 'supply_loss', 'country': 'RU', 'commodity': 'tea'}, ValueError),
                               ({'kind': 'supply_loss', 'country': 'ZZ'}, ce.UnknownCountry)):
            with pytest.raises(error):
                ce.run(graph, trigger)
