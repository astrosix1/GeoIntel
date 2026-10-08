"""Government tab: structured Factbook government, V-Dem (bundled), Wikidata office holders, Wikipedia intro, the AI summary."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from data_sources import wikidata, wikipedia
from data_sources.factbook import parse_profile
from services import country_data as bundled
from services import country_government as cg
from services import country_power as power

FIX = Path(__file__).parent / 'fixtures' / 'factbook'


def gov(name):
    return parse_profile(json.loads((FIX / f'{name}.json').read_text(encoding='utf-8')))['government']


class TestFactbookGovernment:
    def test_two_chambers_with_seats_elections_and_women(self):
        legislature = gov('fr')['legislature']
        assert legislature['structure'] == 'bicameral' and [c['label'] for c in legislature['chambers']] == ['lower chamber', 'upper chamber']
        lower = legislature['chambers'][0]
        assert lower['seats'].startswith('577') and lower['women_percent'] == '36.2%' and lower['next_election'] == 'June 2029'

    def test_a_one_chamber_legislature_keeps_its_figures(self):
        chambers = gov('sy')['legislature']['chambers']
        assert len(chambers) == 1 and chambers[0]['label'] == 'unicameral' and chambers[0]['seats'].startswith('210')

    def test_courts_executive_dates_citizenship_and_parties(self):
        fr = gov('fr')
        assert fr['judiciary']['highest_courts'].startswith('Court of Cassation')
        assert fr['next_election'] == 'April 2027' and fr['independence'] and fr['administrative_divisions']
        assert fr['citizenship']['dual citizenship recognized'] == 'yes'
        assert fr['parties'][0] == 'Citizen and Republican Movement or MRC' and len(fr['parties']) > 10

    def test_memberships_are_kept(self):
        assert any(m['abbr'] == 'NATO' for m in gov('fr')['memberships'])


class TestBundled:
    def test_democracy_has_value_rank_regime_and_trend(self):
        fr = bundled.democracy('FR')
        assert 0.8 < fr['value'] <= 1 and fr['regime']['label'] == 'Liberal democracy' and fr['series'][0][0] == 1950
        assert bundled.democracy('FR')['rank'] < bundled.democracy('SY')['rank']
        assert bundled.democracy('ZZ') is None


class TestWikidata:
    @pytest.fixture(autouse=True)
    def fresh(self):
        with patch('data_sources.wikidata.cache_get', return_value=None), patch('data_sources.wikidata.cache_set'):
            yield

    def _response(self, rows):
        return MagicMock(status_code=200, json=lambda: {'results': {'bindings': rows}})

    def _row(self, name, start=None, end=None):
        row = {'l': {'value': name}}
        if start:
            row['start'] = {'value': start + 'T00:00:00Z'}
        if end:
            row['end'] = {'value': end + 'T00:00:00Z'}
        return row

    def test_holders_newest_first_with_dates_and_unlabelled_items_left_out(self):
        rows = [self._row('Now Person', '2025-01-01'), self._row('Q123', '2020-01-01', '2024-12-31'), self._row('Before', '2015-01-01', '2019-12-31'),
                self._row('Before', '2015-01-01', '2019-12-31')]
        with patch('data_sources.wikidata.requests') as req:
            req.Timeout = req.ConnectionError = Exception
            req.get.return_value = self._response(rows)
            out = wikidata.leaders('FR')
        assert [h['name'] for h in out['head_of_state']] == ['Now Person', 'Before']  # the Q-number and the repeat are gone
        assert out['head_of_state'][1] == {'name': 'Before', 'start': '2015-01-01', 'end': '2019-12-31'}
        assert out['source'].startswith('Wikidata')

    def test_bad_code_or_failure_is_none(self):
        assert wikidata.leaders("FR' }") is None
        with patch('data_sources.wikidata.requests') as req:
            req.Timeout = req.ConnectionError = Exception
            req.get.return_value = MagicMock(status_code=500)
            assert wikidata.leaders('FR') is None


class TestWikipedia:
    @pytest.fixture(autouse=True)
    def fresh(self):
        with patch('data_sources.wikipedia.cache_get', return_value=None), patch('data_sources.wikipedia.cache_set'):
            yield

    def test_intro_carries_its_attribution(self):
        page = {'type': 'standard', 'title': 'Politics of France', 'extract': 'France is a republic. ' * 3,
                'content_urls': {'desktop': {'page': 'https://en.wikipedia.org/wiki/Politics_of_France'}}}
        with patch('data_sources.wikipedia._summary', side_effect=lambda t: page if t == 'Politics of France' else None):
            out = wikipedia.politics_intro('FR')
        assert out['license'] == 'CC BY-SA 4.0' and out['url'].endswith('Politics_of_France') and 'republic' in out['extract']

    def test_long_extracts_are_cut_at_a_sentence(self):
        page = {'type': 'standard', 'title': 'T', 'extract': 'A sentence of some length. ' * 100, 'content_urls': {}}
        with patch('data_sources.wikipedia._summary', return_value=page):
            out = wikipedia.politics_intro('FR')
        assert len(out['extract']) <= wikipedia.MAX_CHARS and out['extract'].endswith('.')

    def test_disambiguation_or_missing_is_none(self):
        with patch('data_sources.wikipedia._summary', return_value=None):
            assert wikipedia.politics_intro('FR') is None


class TestPower:
    def _message(self, text):
        return SimpleNamespace(content=[SimpleNamespace(text=text)])

    @pytest.fixture(autouse=True)
    def fresh(self):
        with patch('services.country_power.cache_get', return_value=None), patch('services.country_power.cache_set'):
            yield

    def test_the_model_only_sees_the_factbook_text(self):
        client = MagicMock(api_key='k')
        client.messages.create.return_value = self._message('{"head_of_state": "The president is elected.", "government": null, "legislature": "Two chambers.", "courts": " ", "constitution": null}')
        with patch('services.country_power.anthropic_client', client):
            out = power.explain('FR', gov('fr'))
        prompt = client.messages.create.call_args.kwargs['messages'][0]['content']
        assert 'Court of Cassation' in prompt and 'only facts stated' in prompt.lower().replace('using only facts stated', 'only facts stated')
        assert out == {'head_of_state': 'The president is elected.', 'government': None, 'legislature': 'Two chambers.', 'courts': None, 'constitution': None}

    def test_no_key_a_bad_reply_or_nothing_to_say_is_none(self):
        with patch('services.country_power.anthropic_client', MagicMock(api_key='')):
            assert power.explain('FR', gov('fr')) is None
        client = MagicMock(api_key='k')
        client.messages.create.return_value = self._message('sorry, no json here')
        with patch('services.country_power.anthropic_client', client):
            assert power.explain('FR', gov('fr')) is None
        client.messages.create.return_value = self._message('{"head_of_state": null, "government": null, "legislature": null, "courts": null, "constitution": null}')
        with patch('services.country_power.anthropic_client', client):
            assert power.explain('FR', gov('fr')) is None
        with patch('services.country_power.anthropic_client', client):
            assert power.explain('FR', {}) is None


class TestTab:
    @patch('services.country_government.explain', return_value={'head_of_state': 'x'})
    @patch('services.country_government.wikipedia')
    @patch('services.country_government.wikidata')
    @patch('services.country_government.FactbookConnector')
    def test_groups_and_sources(self, fb, wd, wp, _explain):
        fb.fetch_profile.return_value = parse_profile(json.loads((FIX / 'fr.json').read_text(encoding='utf-8')))
        wd.leaders.return_value = {'head_of_state': [], 'source': 'Wikidata (CC0)'}
        wp.politics_intro.return_value = {'license': 'CC BY-SA 4.0', 'extract': 'x'}
        out = cg.build_tab('FR')
        assert 'memberships' not in out['government'] and out['memberships'][0]['kind'] == 'security'
        assert out['democracy']['regime']['label'] == 'Liberal democracy' and out['power'] == {'head_of_state': 'x'}
        assert 'Wikipedia (CC BY-SA 4.0)' in out['sources'] and 'Wikidata (CC0)' in out['sources']

    @patch('services.country_government.explain', return_value=None)
    @patch('services.country_government.wikipedia')
    @patch('services.country_government.wikidata')
    @patch('services.country_government.FactbookConnector')
    def test_nothing_anywhere_is_none(self, fb, wd, wp, _explain):
        fb.fetch_profile.return_value = None
        wd.leaders.return_value = None
        wp.politics_intro.return_value = None
        assert cg.build_tab('ZZ') is None
