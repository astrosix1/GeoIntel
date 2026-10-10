"""The cascade triggers (templates, merging the two directions) and the premium API."""
import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from extensions import limiter
from models import Crisis
from services import cascade_triggers as ct
from services.cascade_graph import build_graph
from test_watchlist import call, secret  # noqa: F401  (the premium-user helpers and fixture)


def partners(*pairs, as_of=2023):
    return {'items': [{'name': n, 'percent': p, 'under': False} for n, p in pairs], 'as_of': as_of}


def profile(exports=None, imports=None, commodities=None):
    return {'economy': {'export_partners': exports, 'import_partners': imports,
                        'exports': {'items': commodities, 'as_of': 2023} if commodities else None}, 'energy_fuels': {}}


@pytest.fixture()
def graph():
    return build_graph({
        'RU': profile(exports=partners(('China', 33), ('Turkey', 10)), imports=partners(('China', 53), ('Germany', 5)), commodities=['natural gas', 'wheat']),
        'DE': profile(exports=partners(('Russia', 3)), imports=partners(('Russia', 5))),
        'TR': profile(exports=partners(('Russia', 6)), imports=partners(('Russia', 9))),
        'CN': profile(exports=partners(('Russia', 2)), imports=partners(('Russia', 4))),
    })


@pytest.fixture(autouse=True)
def fresh_limits(app_module):
    limiter.reset()
    yield


class TestTemplates:
    def test_attack_runs_both_directions_and_merges_one_effect_per_country(self, graph):
        result = ct.run_template(graph, 'attack', 'RU')
        isos = [e['iso'] for e in result['effects']]
        assert len(isos) == len(set(isos))                                  # one entry per country
        tr = next(e for e in result['effects'] if e['iso'] == 'TR')
        assert tr['mechanisms'] == ['Supply loss: trade dependence', 'Demand loss: export dependence']
        assert len(tr['evidence']) == 2 and tr['exposure'] == 'Moderate'      # 9% of its imports and 6% of its exports: Moderate both ways
        assert result['trigger']['template'] == 'attack' and result['assumes']

    def test_export_ban_needs_a_commodity_and_runs_supply_loss_only(self, graph):
        with pytest.raises(ct.BadTrigger):
            ct.run_template(graph, 'export_ban', 'RU')
        result = ct.run_template(graph, 'export_ban', 'RU', 'gas')
        assert all(e['mechanisms'] == ['Supply loss: trade dependence'] or 'Supply loss' in e['mechanism'] for e in result['effects'])
        assert result['trigger']['commodity_label'] == 'Natural gas'

    def test_an_embargo_on_one_commodity_runs_the_supply_side_only(self, graph):
        result = ct.run_template(graph, 'embargo', 'RU', 'gas')
        assert all('Demand loss' not in m for e in result['effects'] for m in e['mechanisms'])
        assert 'exports of natural gas are cut off' in result['assumes']
        assert any('Demand loss' in m for e in ct.run_template(graph, 'embargo', 'RU')['effects'] for m in e['mechanisms'])

    def test_commodity_is_ignored_for_templates_that_take_none(self, graph):
        assert ct.run_template(graph, 'attack', 'RU', 'gas')['trigger']['commodity'] is None

    def test_bad_input(self, graph):
        for args in (('nope', 'RU', None), ('embargo', 'RU', 'tea')):
            with pytest.raises(ct.BadTrigger):
                ct.run_template(graph, *args)
        with pytest.raises(Exception):
            ct.run_template(graph, 'attack', 'ZZ')

    def test_the_event_type_picks_the_template(self):
        assert ct.trigger_for_event('conflict', 'UA')[0] == 'attack'
        assert ct.trigger_for_event('economic', 'IR')[0] == 'embargo'
        assert ct.trigger_for_event('something_else', 'UA')[0] == 'attack'
        assert 'attack' not in ct.trigger_for_event('conflict', 'UA')[1].lower() or 'treated as' in ct.trigger_for_event('conflict', 'UA')[1]

    def test_options_list_templates_and_commodities_and_no_chokepoint_yet(self):
        opts = ct.options()
        assert {t['key'] for t in opts['templates']} == {'attack', 'embargo', 'export_ban', 'hazard', 'collapse'}
        assert {c['key'] for c in opts['commodities']} >= {'gas', 'oil', 'grain', 'chips'}

    def test_no_probability_wording(self, graph):
        assert 'probab' not in json.dumps(ct.run_template(graph, 'attack', 'RU')).lower()


class TestApi:
    def test_requires_a_premium_user(self, client, secret):  # noqa: F811
        assert call(client, 'post', '/api/cascade/run', json={}).status_code == 401
        assert call(client, 'get', '/api/cascade/options').status_code == 401
        user = str(uuid.uuid4())
        assert call(client, 'post', '/api/cascade/run', user, plan=None, json={}).status_code == 403
        assert call(client, 'get', '/api/cascade/options', user, plan=None).status_code == 403

    def test_503_while_the_graph_is_warming_and_it_starts_the_build(self, client, secret):  # noqa: F811
        with patch('blueprints.cascade.cached_graph', return_value=None), patch('blueprints.cascade.warm_graph_async') as warm:
            res = call(client, 'post', '/api/cascade/run', str(uuid.uuid4()), json={'template': 'attack', 'country': 'RU'})
            assert res.status_code == 503 and res.get_json()['error'] == 'cascade_warming'
            assert call(client, 'get', '/api/cascade/options', str(uuid.uuid4())).status_code == 503
        assert warm.call_count == 2

    def test_run_and_options(self, client, secret, graph):  # noqa: F811
        user = str(uuid.uuid4())
        with patch('blueprints.cascade.cached_graph', return_value=graph), patch('blueprints.cascade.cascade_trade.load', return_value=None):
            opts = call(client, 'get', '/api/cascade/options', user).get_json()
            assert {'iso': 'RU', 'name': 'Russia'} in opts['countries'] and opts['templates'] and opts['commodities']
            res = call(client, 'post', '/api/cascade/run', user, json={'template': 'embargo', 'country': 'ru', 'commodity': 'gas'})
            assert res.status_code == 200
            data = res.get_json()
            assert data['trigger']['country'] == 'RU' and data['counts'] and data['not_modelled'] and data['method']

    @pytest.mark.parametrize('body', [None, [], {}, {'template': 'attack'}, {'template': 5, 'country': 'RU'}, {'template': 'nope', 'country': 'RU'},
                                      {'template': 'export_ban', 'country': 'RU'}, {'template': 'embargo', 'country': 'RU', 'commodity': 9}])
    def test_invalid_triggers_are_400(self, client, secret, graph, body):  # noqa: F811
        with patch('blueprints.cascade.cached_graph', return_value=graph):
            assert call(client, 'post', '/api/cascade/run', str(uuid.uuid4()), json=body).status_code == 400

    def test_unknown_country_is_404(self, client, secret, graph):  # noqa: F811
        with patch('blueprints.cascade.cached_graph', return_value=graph):
            assert call(client, 'post', '/api/cascade/run', str(uuid.uuid4()), json={'template': 'attack', 'country': 'ZZ'}).status_code == 404

    def test_start_from_an_event(self, client, secret, graph, db_session):  # noqa: F811
        db_session.query(Crisis).filter(Crisis.id == 'casc-1').delete()
        db_session.add(Crisis(id='casc-1', type='conflict', title='Fighting', country='Russia', latitude=55, longitude=37, severity=70, is_active=True,
                              date_start=datetime.utcnow()))
        db_session.commit()
        with patch('blueprints.cascade.cached_graph', return_value=graph), patch('blueprints.cascade.cascade_trade.load', return_value=None):
            res = call(client, 'post', '/api/cascade/run', str(uuid.uuid4()), json={'crisis_id': 'casc-1'})
            assert res.status_code == 200
            data = res.get_json()
            assert data['trigger']['template'] == 'attack' and data['trigger']['country'] == 'RU' and 'treated as' in data['started_from']
            assert call(client, 'post', '/api/cascade/run', str(uuid.uuid4()), json={'crisis_id': 'nope'}).status_code == 404
        db_session.query(Crisis).filter(Crisis.id == 'casc-1').delete()
        db_session.commit()


class TestWhatWouldChange:
    @pytest.fixture()
    def graph(self):
        fuels = lambda p, c: {'gas': {'production': {'value': p, 'unit': 'm3', 'as_of': 2023}, 'consumption': {'value': c, 'unit': 'm3', 'as_of': 2023}}}
        return build_graph({
            'RU': {**profile(commodities=['natural gas']), 'energy_fuels': fuels(600e9, 470e9)},
            'QA': {**profile(imports=partners(('Russia', 1))), 'energy_fuels': fuels(180e9, 40e9)},
            'NO': {**profile(imports=partners(('Russia', 1))), 'energy_fuels': fuels(120e9, 5e9)},
            'TR': {**profile(imports=partners(('Russia', 30), ('Iran', 12), ('Azerbaijan', 9), ('Algeria', 7))), 'energy_fuels': fuels(0.4e9, 50e9)},
        })

    def test_lists_other_net_exporters_and_the_other_suppliers_of_the_most_exposed(self, graph):
        result = ct.run_template(graph, 'export_ban', 'RU', 'gas')
        texts = [w['text'] for w in result['would_change']]
        assert texts[0].startswith('Other countries that produce more natural gas than they use: Qatar (140 bcm), Norway (115 bcm)')
        assert any(t.startswith("Turkey's other main import partners (all goods, not necessarily natural gas): Iran 12%, Azerbaijan 9%, Algeria 7%") for t in texts)
        assert all('Russia' not in t.split(':')[1] for t in texts[:1])           # the trigger country is never offered as an alternative
        assert all(w['source'] for w in result['would_change'])

    def test_nothing_is_invented_when_no_data(self, graph):
        assert ct.run_template(graph, 'attack', 'RU')['would_change'] == [] or all('Other countries' not in w['text'] for w in ct.run_template(graph, 'attack', 'RU')['would_change'])
