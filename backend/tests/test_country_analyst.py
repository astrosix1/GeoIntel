"""The analyst read: fact sheet per tab, the model call, caching, and the endpoint."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from blueprints.countries import countries_bp
from services import country_analyst as ca

STAT = {'label': 'GDP', 'value': 3366315927447.0, 'unit': 'US$', 'year': 2025, 'rank': 7, 'of': 214, 'series': [[1991, 1000.0], [2025, 2670.0]]}


class TestFactSheet:
    def test_a_figure_carries_its_year_rank_and_trend(self):
        line = ca._stat_line(STAT)
        assert '3,366,315,927,447' in line and '(2025)' in line and 'rank 7 of 214' in line and 'up 167% since 1991' in line

    def test_a_series_that_touches_zero_gives_only_its_start(self):
        assert ca._trend([[1990, 0.5], [2000, -2.0], [2025, 4.5]]) == ', was 0.5 in 1990'

    def test_each_tab_reads_only_its_own_data(self):
        assert ca._lines('economy', {'stats': [STAT]})[0].startswith('GDP:')
        assert ca._lines('government', {'government': {'type': 'republic', 'chief_of_state': {'text': 'President X'}}}) == [
            'Government type: republic', 'Head of state: President X']
        security = ca._lines('security', {'advisory': {'alerts': []}, 'conflicts': {'days': 30, 'total': 5, 'last_7_days': 2, 'weekly': [['2026-10-01', 2]], 'hotspots': [{'name': None, 'count': 3}]}})
        assert security[0] == 'UK travel advice: no warnings in force' and 'unnamed area (3)' in security[2]
        geography = ca._lines('geography', {'hazards': {'items': []}})
        assert geography == ['Hazards active now: none']

    def test_no_data_means_no_lines(self):
        for tab in ('government', 'people', 'migration', 'economy', 'security', 'geography'):
            assert ca._lines(tab, {}) == []


class TestRead:
    def _client(self, text='A paragraph.'):
        client = MagicMock(api_key='k')
        client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text=text)])
        return client

    @pytest.fixture(autouse=True)
    def fresh(self):
        with patch('services.country_analyst.cache_get', return_value=None), patch('services.country_analyst.cache_set') as self.set:
            yield

    def test_the_model_sees_only_the_fact_sheet_and_the_result_is_kept(self):
        client = self._client(' A paragraph. ')
        with patch('services.country_analyst.anthropic_client', client):
            out = ca.read('FR', 'France', 'economy', {'stats': [STAT]})
        prompt = client.messages.create.call_args.kwargs['messages'][0]['content']
        assert 'GDP: 3,366,315,927,447' in prompt and 'Use ONLY the facts below' in prompt and 'France' in prompt
        assert out['text'] == 'A paragraph.' and self.set.called

    def test_a_cached_read_does_not_call_the_model(self):
        client = self._client()
        with patch('services.country_analyst.anthropic_client', client), patch('services.country_analyst.cache_get', return_value={'text': 'kept', 'model': 'm'}):
            assert ca.read('FR', 'France', 'economy', {'stats': [STAT]})['text'] == 'kept'
        client.messages.create.assert_not_called()

    def test_no_data_no_key_or_a_failing_model_raise_unavailable(self):
        with patch('services.country_analyst.anthropic_client', self._client()):
            with pytest.raises(ca.AnalystUnavailable) as e:
                ca.read('FR', 'France', 'economy', {})
            assert e.value.reason == 'no_data'
        with patch('services.country_analyst.anthropic_client', MagicMock(api_key='')):
            with pytest.raises(ca.AnalystUnavailable) as e:
                ca.read('FR', 'France', 'economy', {'stats': [STAT]})
            assert e.value.reason == 'no_model'
        failing = MagicMock(api_key='k')
        failing.messages.create.side_effect = RuntimeError('down')
        with patch('services.country_analyst.anthropic_client', failing):
            with pytest.raises(ca.AnalystUnavailable) as e:
                ca.read('FR', 'France', 'economy', {'stats': [STAT]})
            assert e.value.reason == 'model_error'


def test_the_endpoint_is_premium_only():
    app = Flask(__name__)
    app.register_blueprint(countries_bp)
    with app.test_client() as c:
        assert c.get('/api/countries/FR/tab/economy/read').status_code in (401, 403)
