"""Factbook parsers, checked against real country files saved in tests/fixtures/factbook (France, China, Niger, Syria, US)."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from data_sources.factbook import FactbookConnector, parse_age_structure, parse_cities, parse_list, parse_profile, parse_rate, parse_shares

FIX = Path(__file__).parent / 'fixtures' / 'factbook'


def _profile(name):
    return parse_profile(json.loads((FIX / f'{name}.json').read_text(encoding='utf-8')))


def test_shares_read_names_and_percentages():
    out = parse_shares('Roman Catholic 47%, Muslim 4%, none 33%, unspecified 9% (2021 est.)')
    assert [(i['name'], i['percent']) for i in out['items']] == [('Roman Catholic', 47.0), ('Muslim', 4.0), ('none', 33.0), ('unspecified', 9.0)]
    assert out['as_of'] == 2021


def test_shares_keep_bracketed_sub_splits_as_children():
    out = parse_shares('Muslim 87% (includes Sunni 74%, and Shia 13%), Christian 10% (2 est.), Druze 3% (2019 est.)')
    assert [i['name'] for i in out['items']] == ['Muslim', 'Christian', 'Druze']
    assert [(c['name'], c['percent']) for c in out['items'][0]['children']] == [('Sunni', 74.0), ('Shia', 13.0)]
    assert 'children' not in out['items'][1] and out['as_of'] == 2019


def test_shares_none_when_no_percentages():
    assert parse_shares('Celtic and Latin with Teutonic, Slavic minorities') is None
    assert parse_shares(None) is None


def test_rate_and_list():
    assert parse_rate('10.88 births/1,000 population (2025 est.)') == {'value': 10.88, 'as_of': 2025}
    assert parse_rate('n/a') is None
    assert parse_list('aircraft, cars, packaged medicine (2023)') == {'items': ['aircraft', 'cars', 'packaged medicine'], 'as_of': 2023}
    assert parse_list('coal (a, b), iron ore') ['items'] == ['coal (a, b)', 'iron ore']


def test_age_structure_gives_counts():
    bands = parse_age_structure({'0-14 years': {'text': '17.3% (male 6,060,087/female 5,792,805)'}, 'note': {'text': 'x'}})
    assert bands == [{'band': '0-14 years', 'percent': 17.3, 'male': 6060087, 'female': 5792805, 'count': 11852892, 'as_of': None}]


def test_real_files():
    fr = _profile('fr')
    assert fr['government']['type'] == 'semi-presidential republic'
    assert 'MACRON' in fr['government']['chief_of_state']['summary']
    assert fr['people']['religions']['items'][0]['name'] == 'Roman Catholic'
    assert fr['people']['ethnic_groups'] is None and fr['people']['ethnic_groups_text']
    assert [b['band'] for b in fr['people']['age_structure']] == ['0-14 years', '15-64 years', '65 years and over']
    assert fr['economy']['exports']['items'][0] == 'aircraft'
    ne = _profile('ng')
    assert ne['people']['ethnic_groups']['items'][0] == {'name': 'Hausa', 'percent': 53.1, 'under': False}
    sy = _profile('sy')
    assert [i['name'] for i in sy['people']['religions']['items']] == ['Muslim', 'Christian', 'Druze']
    assert parse_profile('nope') is None


@patch('data_sources.factbook.requests')
def test_fetch_profile(mock_requests):
    resp = MagicMock(status_code=200)
    resp.json.return_value = json.loads((FIX / 'fr.json').read_text(encoding='utf-8'))
    mock_requests.get.return_value = resp
    with patch('data_sources.factbook.cache_get', return_value=None), patch('data_sources.factbook.cache_set'):
        assert FactbookConnector.fetch_profile('FR')['government']['type'] == 'semi-presidential republic'
        assert 'europe/fr.json' in mock_requests.get.call_args[0][0]
        assert FactbookConnector.fetch_profile('ZZ') is None
        mock_requests.get.return_value = MagicMock(status_code=404)
        assert FactbookConnector.fetch_profile('DE') is None


def test_cities_read_population_names_and_the_capital():
    out = parse_cities('11.208 million PARIS (capital), 1.761 million Lyon, 996,000 Hamah (2023)')
    assert out['as_of'] == 2023
    assert out['items'] == [{'name': 'Paris', 'population': 11208000, 'capital': True},
                            {'name': 'Lyon', 'population': 1761000, 'capital': False},
                            {'name': 'Hamah', 'population': 996000, 'capital': False}]
    assert parse_cities(None) is None and parse_cities('no numbers here') is None


def test_language_shares_keep_the_first_entry_when_it_has_a_bracketed_note():
    out = parse_shares('English only (official) 78.2%, Spanish 13.4%, other 7.3% (2017 est.)')
    assert [(i['name'], i['percent']) for i in out['items']] == [('English only', 78.2), ('Spanish', 13.4), ('other', 7.3)]


def test_real_files_give_languages_and_cities():
    us = _profile('us')['people']
    assert us['language_shares']['items'][0]['name'] == 'English only'
    fr = _profile('fr')['people']
    assert fr['languages'].startswith('French') and fr['language_shares'] is not None
    assert fr['major_cities']['items'][0]['name'] == 'Paris' and fr['major_cities']['items'][0]['capital']
