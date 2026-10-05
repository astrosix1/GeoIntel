"""Branch scenarios: validation of model output, generation (with a fake
Anthropic client), caching, and the premium-gated endpoint."""
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest

from cache import cache_delete
from models import Crisis
from services import entitlements, scenarios
from services.ai_client import AI_MODEL
from services.scenarios import ScenariosUnavailable, _validate, generate_scenarios

SECRET = 'jwt-signing-secret'


def scenario(**overrides):
    base = {
        'title': 'Talks resume',
        'likelihood': 'plausible',
        'timeframe': 'weeks',
        'summary': 'Both sides return to negotiations after mediation.',
        'what_would_drive_it': ['Mediation by a neutral party'],
        'watch_for': ['A ceasefire announcement'],
        'who_is_affected': ['Civilians in the region'],
    }
    base.update(overrides)
    return base


def payload(n=3, **overrides):
    titles = ['Talks resume', 'Stalemate continues', 'Fighting escalates', 'Regional spillover']
    likelihoods = ['plausible', 'more likely', 'less likely', 'less likely']
    return {
        'scenarios': [scenario(title=titles[i], likelihood=likelihoods[i], **overrides) for i in range(n)],
        'assumptions': ['No new outside intervention'],
    }


class FakeAnthropic:
    """Stands in for the Anthropic client; records every create() call."""

    def __init__(self, response=None, error=None, api_key='test-key'):
        self.api_key = api_key
        self.calls = []
        self._response = response
        self._error = error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        content = [] if self._response is None else [SimpleNamespace(type='tool_use', input=self._response)]
        return SimpleNamespace(content=content)


@pytest.fixture()
def crisis_id(app_module, client, db_session):
    client.get('/api/health')  # let the app's first-request seeding happen now
    cid = f'scn-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(
        id=cid, type='conflict', title='Border clashes escalate', country='Testland',
        latitude=1, longitude=2, severity=72, source='GDELT', source_url='https://example.com/a',
        is_active=True,
    ))
    db_session.commit()
    cache_delete(f'scenarios:{cid}')
    yield cid
    cache_delete(f'scenarios:{cid}')
    db_session.query(Crisis).filter(Crisis.id == cid).delete()
    db_session.commit()


@pytest.fixture(autouse=True)
def no_network():
    with patch.object(scenarios, 'fetch_real_page_metadata', return_value={'description': 'Troops exchanged fire near the border.'}):
        yield


class TestValidate:
    def test_valid_payload(self):
        scenarios_out, assumptions = _validate(payload(3))
        assert [s['title'] for s in scenarios_out] == ['Talks resume', 'Stalemate continues', 'Fighting escalates']
        assert assumptions == ['No new outside intervention']

    def test_likelihood_is_normalised_to_lowercase(self):
        out, _ = _validate({'scenarios': [scenario(likelihood='Plausible'), scenario(title='B'), scenario(title='C')], 'assumptions': []})
        assert out[0]['likelihood'] == 'plausible'

    def test_unknown_likelihood_scenario_is_dropped(self):
        data = payload(3)
        data['scenarios'][0]['likelihood'] = 'very likely'
        out, _ = _validate(data)
        assert len(out) == 2

    @pytest.mark.parametrize('text', [
        'There is a 40% chance talks resume.',
        'Roughly a 30 percent probability of escalation.',
        'The probability of collapse is about 60.',
        'Odds are 2 to 1 against.',
    ])
    def test_numeric_probability_scenarios_are_dropped(self, text):
        data = payload(3)
        data['scenarios'][1]['summary'] = text
        out, _ = _validate(data)
        assert len(out) == 2
        assert all(text != s['summary'] for s in out)

    def test_ordinary_percentages_are_not_treated_as_probabilities(self):
        data = payload(3)
        data['scenarios'][0]['summary'] = 'About 40% of residents would be displaced.'
        out, _ = _validate(data)
        assert len(out) == 3

    def test_probability_in_assumptions_is_dropped(self):
        data = payload(3)
        data['assumptions'] = ['A 20% chance of intervention', 'Supply lines stay open']
        _, assumptions = _validate(data)
        assert assumptions == ['Supply lines stay open']

    def test_fewer_than_two_valid_scenarios_raises(self):
        data = payload(3)
        data['scenarios'][0]['likelihood'] = 'nope'
        data['scenarios'][1]['title'] = ''
        with pytest.raises(ScenariosUnavailable) as exc:
            _validate(data)
        assert exc.value.reason == 'invalid_model_output'

    @pytest.mark.parametrize('bad', [None, [], 'text', {'scenarios': 'x'}, {}])
    def test_malformed_payload_raises(self, bad):
        with pytest.raises(ScenariosUnavailable):
            _validate(bad)

    def test_lists_and_lengths_are_capped(self):
        data = payload(3)
        data['scenarios'][0]['watch_for'] = [f'signal {i}' for i in range(20)]
        data['scenarios'][0]['summary'] = 'x' * 5000
        out, _ = _validate(data)
        assert len(out[0]['watch_for']) == 5
        assert len(out[0]['summary']) == 700

    def test_at_most_four_scenarios(self):
        data = {'scenarios': [scenario(title=f'S{i}') for i in range(8)], 'assumptions': []}
        out, _ = _validate(data)
        assert len(out) == 4


class TestGenerate:
    def test_happy_path(self, crisis_id):
        fake = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', fake):
            result = generate_scenarios(crisis_id)
        assert len(result['scenarios']) == 3
        assert result['model'] == AI_MODEL
        assert result['disclaimer']
        assert result['based_on']['severity'] == 72
        assert result['based_on']['source_text'] is True
        call = fake.calls[0]
        assert call['model'] == AI_MODEL
        assert call['tool_choice'] == {'type': 'tool', 'name': 'record_scenarios'}
        assert call['tools'][0]['name'] == 'record_scenarios'
        prompt = call['messages'][0]['content']
        assert 'Border clashes escalate' in prompt
        assert 'Troops exchanged fire near the border.' in prompt
        assert 'NEVER give percentages' in prompt

    def test_result_is_cached_so_a_second_call_costs_nothing(self, crisis_id):
        fake = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', fake):
            first = generate_scenarios(crisis_id)
            second = generate_scenarios(crisis_id)
        assert len(fake.calls) == 1
        assert first == second

    def test_failure_is_not_cached(self, crisis_id):
        broken = FakeAnthropic(error=RuntimeError('model down'))
        with patch.object(scenarios, 'anthropic_client', broken):
            with pytest.raises(ScenariosUnavailable) as exc:
                generate_scenarios(crisis_id)
        assert exc.value.reason == 'model_error'
        working = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', working):
            assert generate_scenarios(crisis_id)['scenarios']
        assert len(working.calls) == 1

    def test_invalid_model_output_is_unavailable_and_not_cached(self, crisis_id):
        bad = FakeAnthropic(response=payload(3, summary='A 50% chance of this happening.'))
        with patch.object(scenarios, 'anthropic_client', bad):
            with pytest.raises(ScenariosUnavailable) as exc:
                generate_scenarios(crisis_id)
        assert exc.value.reason == 'invalid_model_output'
        assert generate_scenarios_cached(crisis_id) is None

    def test_no_tool_use_block_is_unavailable(self, crisis_id):
        empty = FakeAnthropic(response=None)
        with patch.object(scenarios, 'anthropic_client', empty):
            with pytest.raises(ScenariosUnavailable) as exc:
                generate_scenarios(crisis_id)
        assert exc.value.reason == 'no_model_output'

    @pytest.mark.parametrize('client_value', [FakeAnthropic(api_key=''), None])
    def test_no_api_key_is_unavailable(self, crisis_id, client_value):
        with patch.object(scenarios, 'anthropic_client', client_value):
            with pytest.raises(ScenariosUnavailable) as exc:
                generate_scenarios(crisis_id)
        assert exc.value.reason == 'ai_not_configured'

    def test_unknown_crisis_returns_none_even_without_a_key(self, app_module):
        with patch.object(scenarios, 'anthropic_client', None):
            assert generate_scenarios('does-not-exist') is None


def generate_scenarios_cached(crisis_id):
    from cache import cache_get
    return cache_get(f'scenarios:{crisis_id}')


def _token(user_id):
    return jwt.encode({'sub': user_id, 'aud': 'authenticated', 'exp': int(time.time()) + 3600},
                      SECRET, algorithm='HS256')


@pytest.fixture()
def user_id(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)
    uid = str(uuid.uuid4())
    cache_delete(f'plan:{uid}')
    yield uid
    cache_delete(f'plan:{uid}')


def _get(client, cid, uid=None, plan_status=None):
    headers = {'Authorization': f'Bearer {_token(uid)}'} if uid else {}
    row = {'status': plan_status} if plan_status else None
    with patch.object(entitlements, '_fetch_subscription', return_value=row):
        return client.get(f'/api/crises/{cid}/scenarios', headers=headers)


class TestEndpoint:
    def test_anonymous_gets_401(self, client, crisis_id):
        res = _get(client, crisis_id)
        assert res.status_code == 401
        assert res.get_json() == {'error': 'sign_in_required'}

    def test_free_user_gets_403(self, client, crisis_id, user_id):
        res = _get(client, crisis_id, user_id)
        assert res.status_code == 403
        assert res.get_json() == {'error': 'premium_required'}

    def test_free_user_never_triggers_a_model_call(self, client, crisis_id, user_id):
        fake = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', fake):
            _get(client, crisis_id, user_id)
        assert fake.calls == []

    def test_premium_user_gets_scenarios(self, client, crisis_id, user_id):
        with patch.object(scenarios, 'anthropic_client', FakeAnthropic(response=payload(3))):
            res = _get(client, crisis_id, user_id, plan_status='active')
        assert res.status_code == 200
        body = res.get_json()
        assert len(body['scenarios']) == 3
        assert body['disclaimer']
        assert {s['likelihood'] for s in body['scenarios']} <= {'less likely', 'plausible', 'more likely'}

    def test_no_api_key_is_503(self, client, crisis_id, user_id):
        with patch.object(scenarios, 'anthropic_client', None):
            res = _get(client, crisis_id, user_id, plan_status='active')
        assert res.status_code == 503
        assert res.get_json() == {'error': 'scenarios_unavailable', 'reason': 'ai_not_configured'}

    def test_unknown_crisis_is_404(self, client, crisis_id, user_id):
        res = _get(client, 'does-not-exist', user_id, plan_status='active')
        assert res.status_code == 404


class TestStoryAware:
    def test_prompt_carries_the_extracted_facts_and_every_source_count(self, crisis_id, db_session):
        import json
        db_session.query(Crisis).filter(Crisis.id == crisis_id).update({
            'facts': json.dumps({'summary': 'A tunnel collapsed.', 'place': 'Obuasi', 'killed': 5, 'injured': None,
                                 'scale_cues': []}),
            'source_count': 3,
        })
        db_session.commit()
        fake = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', fake):
            generate_scenarios(crisis_id)
        prompt = fake.calls[0]['messages'][0]['content']
        assert 'Killed (stated in the article): 5' in prompt and 'merges reports from 3 outlets' in prompt

    def test_a_new_source_or_new_facts_rebuilds_the_cached_scenarios(self, crisis_id, db_session):
        fake = FakeAnthropic(response=payload(3))
        with patch.object(scenarios, 'anthropic_client', fake):
            generate_scenarios(crisis_id)
            generate_scenarios(crisis_id)
            assert len(fake.calls) == 1
            db_session.query(Crisis).filter(Crisis.id == crisis_id).update({'source_count': 2})
            db_session.commit()
            generate_scenarios(crisis_id)
        assert len(fake.calls) == 2
