"""Saved cascade scenarios and the optional written summary."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from extensions import limiter
from services import cascade_narrative as cn, cascade_saved as cs, supabase_rest
from services.cascade_graph import build_graph
from services.cascade_triggers import run_template
from services.supabase_rest import SupabaseUnavailable
from supabase_fake import FakePostgrest
from test_cascade_api import partners, profile
from test_watchlist import call, secret  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_limits(app_module):
    limiter.reset()
    yield


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


@pytest.fixture()
def graph():
    return build_graph({
        'RU': profile(exports=partners(('China', 33), ('Turkey', 10)), imports=partners(('China', 53)), commodities=['natural gas']),
        'TR': profile(exports=partners(('Russia', 6)), imports=partners(('Russia', 9))),
        'CN': profile(exports=partners(('Russia', 2)), imports=partners(('Russia', 4))),
    })


@pytest.fixture()
def result(graph):
    return run_template(graph, 'embargo', 'RU')


def uid():
    return str(uuid.uuid4())


class TestService:
    def test_save_list_get_delete_are_scoped_to_the_user(self, db, result):
        user, other = uid(), uid()
        saved = cs.save(user, '  Gas   embargo ', {'template': 'embargo', 'country': 'RU'}, result)
        assert saved['name'] == 'Gas embargo' and saved['request'] == {'template': 'embargo', 'country': 'RU'}
        assert [s['name'] for s in cs.list_saved(user)] == ['Gas embargo'] and cs.list_saved(other) == []
        assert cs.get(user, saved['id'])['result']['trigger']['country'] == 'RU'
        assert cs.get(other, saved['id']) is None
        cs.delete(other, saved['id'])
        assert cs.get(user, saved['id']) is not None                      # another user cannot delete it
        cs.delete(user, saved['id'])
        assert cs.get(user, saved['id']) is None

    @pytest.mark.parametrize('name', ['', '   ', 'x' * 81, None, 5, '\x00\x01'])
    def test_bad_names(self, db, result, name):
        with pytest.raises(cs.InvalidScenario):
            cs.save(uid(), name, {}, result)

    def test_limit(self, db, result):
        user = uid()
        for i in range(cs.MAX_SAVED):
            cs.save(user, f'n{i}', {}, result)
        with pytest.raises(cs.ScenarioLimitReached):
            cs.save(user, 'one too many', {}, result)

    def test_a_huge_result_is_cut_to_its_most_exposed_effects(self, db, result):
        huge = {**result, 'effects': [{**result['effects'][0], 'iso': f'X{i}', 'caveats': ['x' * 4000]} for i in range(200)]}
        stored = cs.compact(huge)
        assert stored['truncated'] is True and len(stored['effects']) == cs.KEPT_IF_TOO_BIG
        assert cs.compact(result) is result

    def test_supabase_failure(self, db):
        db.fail = True
        with pytest.raises(SupabaseUnavailable):
            cs.list_saved(uid())


class TestApi:
    def test_requires_premium(self, client, secret):  # noqa: F811
        for method, path in (('get', '/api/cascade/saved'), ('post', '/api/cascade/saved'), ('get', f'/api/cascade/saved/{uuid.uuid4()}'),
                             ('delete', f'/api/cascade/saved/{uuid.uuid4()}'), ('post', '/api/cascade/narrative')):
            assert call(client, method, path, json={}).status_code == 401
            assert call(client, method, path, uid(), plan=None, json={}).status_code == 403

    def test_save_runs_the_trigger_server_side_and_stores_that_result(self, client, secret, db, graph):  # noqa: F811
        user = uid()
        with patch('blueprints.cascade.cached_graph', return_value=graph), patch('blueprints.cascade.cascade_trade.load', return_value=None):
            res = call(client, 'post', '/api/cascade/saved', user, json={'name': 'Embargo on Russia', 'template': 'embargo', 'country': 'ru',
                                                                          'result': {'effects': ['forged']}})
            assert res.status_code == 201
            scenario = res.get_json()['scenario']
            assert scenario['request'] == {'template': 'embargo', 'country': 'RU'}
            listed = call(client, 'get', '/api/cascade/saved', user).get_json()
            assert [s['name'] for s in listed['scenarios']] == ['Embargo on Russia'] and listed['limit'] == 20
            full = call(client, 'get', f"/api/cascade/saved/{scenario['id']}", user).get_json()['scenario']
            assert full['result']['trigger']['country'] == 'RU' and 'forged' not in json.dumps(full)      # a client cannot store its own result
            assert call(client, 'get', f"/api/cascade/saved/{uuid.uuid4()}", user).status_code == 404
            assert call(client, 'get', '/api/cascade/saved/not-a-uuid', user).status_code == 404
            assert call(client, 'delete', f"/api/cascade/saved/{scenario['id']}", user).status_code == 204
            assert call(client, 'get', '/api/cascade/saved', user).get_json()['scenarios'] == []

    def test_bad_name_bad_trigger_and_limit(self, client, secret, db, graph):  # noqa: F811
        user = uid()
        with patch('blueprints.cascade.cached_graph', return_value=graph), patch('blueprints.cascade.cascade_trade.load', return_value=None):
            assert call(client, 'post', '/api/cascade/saved', user, json={'name': '', 'template': 'embargo', 'country': 'RU'}).status_code == 400
            assert call(client, 'post', '/api/cascade/saved', user, json={'name': 'x', 'template': 'nope', 'country': 'RU'}).status_code == 400
            for i in range(cs.MAX_SAVED):
                assert call(client, 'post', '/api/cascade/saved', user, json={'name': f'n{i}', 'template': 'embargo', 'country': 'RU'}).status_code == 201
                limiter.reset()
            assert call(client, 'post', '/api/cascade/saved', user, json={'name': 'more', 'template': 'embargo', 'country': 'RU'}).status_code == 409

    def test_supabase_down_is_503(self, client, secret, db):  # noqa: F811
        db.fail = True
        res = call(client, 'get', '/api/cascade/saved', uid())
        assert res.status_code == 503 and res.get_json()['error'] == 'user_data_unavailable'


class FakeClient:
    api_key = 'k'

    def __init__(self, text):
        self.texts = [text] if isinstance(text, str) else list(text)
        self.calls = 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class TestNarrative:
    def test_the_fact_sheet_has_only_the_results_own_facts(self, result):
        facts = cn.facts_for(result)
        assert 'Trigger: Sanctions or an embargo on a country: Russia' in facts and 'Not modelled:' in facts and 'Russia supplies' in facts

    @pytest.mark.parametrize('text,ok', [
        ('Turkey is exposed through trade, and the effects would come within weeks.', True),
        ('China gets 4% of its imports from Russia.', True),                                             # 4 is in the facts
        ('Turkey will lose 45% of its imports.', False),
        ('There is a high chance Turkey is hit.', False),
        ('Exposure of 77 countries is likely.', False),                                               # 77 is not in the facts
    ])
    def test_grounding_check(self, result, text, ok):
        facts = cn.facts_for(result)
        assert (cn._grounded(text, facts) is None) == ok

    def test_returns_text_and_caches(self, result):
        client = FakeClient('Turkey is exposed through trade with Russia, within weeks to months. The analysis does not cover prices.')
        with patch.object(cn, 'anthropic_client', client):
            first = cn.narrate(result)
            second = cn.narrate(result)
        assert first['text'].startswith('Turkey is exposed') and second == first and client.calls == 1

    def test_one_retry_then_unavailable(self, result):
        bad = 'Turkey will lose 99% of its imports.'
        good = 'Turkey is exposed through trade with Russia. The analysis does not cover prices.'
        with patch.object(cn, 'anthropic_client', FakeClient([bad, good])), patch.object(cn, 'cache_get', return_value=None), patch.object(cn, 'cache_set'):
            assert cn.narrate(result)['text'] == good
        with patch.object(cn, 'anthropic_client', FakeClient([bad + ' a', bad + ' b'])), patch.object(cn, 'cache_get', return_value=None):
            with pytest.raises(cn.NarrativeUnavailable) as caught:
                cn.narrate(result)
        assert caught.value.reason == 'ungrounded'

    def test_no_model_and_no_effects(self, result):
        with patch.object(cn, 'anthropic_client', None):
            with pytest.raises(cn.NarrativeUnavailable) as caught:
                cn.narrate(result)
        assert caught.value.reason == 'no_model'
        with pytest.raises(cn.NarrativeUnavailable):
            cn.narrate({**result, 'effects': []})

    def test_endpoint(self, client, secret, graph):  # noqa: F811
        with patch('blueprints.cascade.cached_graph', return_value=graph), patch('blueprints.cascade.cascade_trade.load', return_value=None), \
                patch.object(cn, 'anthropic_client', None):
            res = call(client, 'post', '/api/cascade/narrative', uid(), json={'template': 'embargo', 'country': 'RU'})
            assert res.status_code == 503 and res.get_json() == {'error': 'narrative_unavailable', 'reason': 'no_model'}
