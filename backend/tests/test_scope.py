"""Global/Local classifier (services/scope.py) against the owner's term lists in data_sources/scope_terms.json."""
import json

import pytest

from services import scope
from services.scope import classify, find_terms


def scope_of(text, **kw):
    return classify(text, **kw)['scope']


class TestTermLists:
    def test_every_group_is_well_formed(self):
        data = json.loads(scope.TERMS_PATH.read_text(encoding='utf-8'))
        names = [g['name'] for g in data['groups']]
        assert len(names) == len(set(names))
        for g in data['groups']:
            assert g['side'] in ('global', 'local') and g['weight'] in (1, 2, 3) and g['case'] in ('sensitive', 'insensitive')
            assert g['terms'] and all(isinstance(t, str) and t.strip() for t in g['terms'])

    @pytest.mark.parametrize('text', ['IMF raises its forecast', 'NATO leaders meet', 'World Bank loan approved', 'OPEC cuts output',
                                      'Brent crude jumps', 'WHO declares emergency', 'EU sanctions Moscow'])
    def test_named_institutions_and_markets_are_global(self, text):
        assert scope_of(text) == 'global'

    @pytest.mark.parametrize('text', ['City council votes on zoning change', 'Mayor opens new library', 'Oneida County budget hearing',
                                      'Local bakery marks ten years', 'Hyperlocal news: street fair this weekend'])
    def test_municipal_and_community_stories_are_local(self, text):
        assert scope_of(text) == 'local'


class TestMatching:
    def test_whole_words_only(self):
        assert find_terms('a queue of funny cuneiform tablets') == []

    def test_acronyms_need_their_capitals(self):
        assert classify('who knows what the un did')['global'] == []
        assert classify('UN chief warns of inaction')['global'] == ['UN']

    def test_plurals_match(self):
        assert 'sanctions' in [t.lower() for t in classify('New sanctions announced')['global']]

    def test_longest_phrase_wins_and_a_term_counts_once(self):
        out = classify('City council meeting tonight; city council meeting again')
        assert out['local'].count('City council meeting') == 1 and 'City council' not in out['local']


class TestRules:
    def test_a_named_institution_beats_local_words(self):
        assert scope_of('Mayor attends UN summit in Geneva') == 'global'

    def test_weak_words_together_do_not_decide(self):
        # war, military and conflict are weak; they only count as one signal
        out = classify('Maine military museum honors war veterans in the conflict')
        assert out['scope'] == 'global' and out['rule'] == 'no match, default'
        assert out['global_score'] == 1

    def test_weak_local_words_alone_stay_on_default(self):
        out = classify('France closes hundreds of schools as student protests spread')
        assert out['rule'] == 'no match, default'

    def test_weak_local_word_with_a_specific_place_is_local(self):
        out = classify('Police investigate theft', place_specific=True)
        assert out['scope'] == 'local' and out['rule'] == 'local terms and a specific place'

    def test_two_different_states_as_actors_block_the_place_rule(self):
        assert scope_of('Police attacks India', place_specific=True, actors_differ=True) == 'global'
        assert scope_of('Police attacks India', place_specific=True, actors_differ=False) == 'local'

    def test_plane_crashes_are_not_local_traffic_accidents(self):
        assert classify('Plane crash kills 40', place_specific=True)['rule'] == 'no match, default'
        assert scope_of('Car crash on Main Street', place_specific=True) == 'local'

    def test_a_specific_place_does_not_override_a_global_term(self):
        assert scope_of('Police probe sanctions evasion', place_specific=True) != 'local'

    def test_noise_signal_stays_local_unless_a_global_term_applies(self):
        assert scope_of('Something happened somewhere', noise=True) == 'local'
        assert scope_of('NATO announces a plan', noise=True) == 'global'

    def test_tie_goes_by_the_actors(self):
        text = 'Treaty and mayor'
        assert scope_of(text, actors_differ=True) == 'global'
        assert scope_of(text, actors_differ=False) == 'local'
        assert classify(text)['rule'] == 'no match, default'

    def test_unmatched_events_keep_the_older_side(self):
        assert classify('Nothing to see here')['rule'] == 'no match, default'
        assert scope_of('Nothing to see here') == 'global'

    def test_the_result_names_what_decided_it(self):
        out = classify('IMF and World Bank meet')
        assert out['global'] == ['World Bank', 'IMF'] or set(out['global']) == {'World Bank', 'IMF'}
        assert out['global_score'] == 6 and out['local'] == []


class TestIngest:
    def test_assign_scope_uses_the_real_headline_pin_precision_and_actors(self):
        from data_sources.gdelt import GDELTConnector as G
        city = {'title': 'Man arrested after car crash in Dayton', 'location_confidence': 85, 'scope': 'global', '_noise': False, '_actors_differ': False}
        out = G._assign_scope(dict(city))
        assert out['scope'] == 'local' and '_noise' not in out and '_actors_differ' not in out
        assert json.loads(out['scope_basis'])['rule'] == 'local terms and a specific place'
        # the same words with a country-level pin and two different actors stay global
        foreign = {**city, 'location_confidence': 55, '_actors_differ': True}
        assert G._assign_scope(dict(foreign))['scope'] == 'global'
        # a named institution beats the old noise signal
        noisy = {'title': 'UN chief warns of famine', 'location_confidence': 55, 'scope': 'local', '_noise': True, '_actors_differ': None}
        assert G._assign_scope(noisy)['scope'] == 'global'

    def test_parse_row_hands_over_the_noise_signal_and_actors(self, app_module):
        from tests.test_gdelt import make_row
        import data_sources as ds
        row = ds.GDELTConnector._parse_row(make_row())
        assert '_noise' in row and '_actors_differ' in row


def test_judge_missing_fills_in_only_unjudged_events_and_is_idempotent(app_module, db_session):
    import uuid
    from datetime import datetime
    from models import Crisis
    ids = []
    for title, old_scope in (('City council votes on zoning', 'global'), ('NATO leaders meet', 'local'), ('Nothing to see', 'global')):
        cid = f'sc-{uuid.uuid4().hex[:8]}'
        ids.append(cid)
        db_session.add(Crisis(id=cid, type='conflict', title=title, country='Testland', latitude=1.0, longitude=1.0, scope=old_scope,
                              source='GDELT', date_start=datetime.utcnow(), location_confidence=55))
    done = Crisis(id=f'sc-{uuid.uuid4().hex[:8]}', type='conflict', title='Mayor opens library', country='Testland', latitude=1.0,
                  longitude=1.0, scope='global', scope_basis='{"v":' + str(scope.terms_version()) + ',"rule":"kept"}', source='GDELT', date_start=datetime.utcnow())
    db_session.add(done)
    db_session.commit()
    db_session.query(Crisis).filter(~Crisis.id.in_(ids + [done.id])).update({'scope_basis': '{"v":' + str(scope.terms_version()) + ',"rule":"x"}'}, synchronize_session=False)
    db_session.commit()

    judged, moved = scope.judge_missing()

    assert judged == 3 and moved == 2
    db_session.expire_all()
    scopes = {r.title: (r.scope, json.loads(r.scope_basis)['rule']) for r in db_session.query(Crisis).filter(Crisis.id.in_(ids))}
    assert scopes['City council votes on zoning'][0] == 'local'
    assert scopes['NATO leaders meet'][0] == 'global'
    assert scopes['Nothing to see'] == ('global', 'no match, default')
    assert json.loads(db_session.get(Crisis, done.id).scope_basis)['rule'] == 'kept'
    assert scope.judge_missing() == (0, 0)


def test_the_event_detail_carries_the_reason(app_module, db_session):
    import uuid
    from datetime import datetime
    from models import Crisis
    cid = f'sc-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(id=cid, type='conflict', title='NATO leaders meet', country='Testland', latitude=1.0, longitude=1.0, scope='global',
                          scope_basis=json.dumps({'rule': 'global terms', 'global': ['NATO'], 'local': []}), source='GDELT',
                          date_start=datetime.utcnow()))
    db_session.commit()
    row = db_session.get(Crisis, cid).to_dict()
    assert row['scope'] == 'global' and row['scope_basis']['global'] == ['NATO']
    db_session.get(Crisis, cid).scope_basis = None
    db_session.commit()
    assert db_session.get(Crisis, cid).to_dict()['scope_basis'] is None


class TestCountyAbbreviation:
    def test_a_county_written_co_is_local(self):
        out = classify("Montgomery Co. considers requiring fire hoods in certain apartment buildings")
        assert out['scope'] == 'local' and out['local'] == ['Montgomery Co.']

    @pytest.mark.parametrize('text', ['Ford Motor Co. recalls trucks', 'Hudson Bay Co. posts loss', 'Standard Oil Co. history'])
    def test_a_company_written_co_is_not(self, text):
        assert classify(text)['local'] == []

    def test_old_verdicts_are_judged_again_when_the_lists_change(self, app_module, db_session):
        import uuid
        from datetime import datetime
        from models import Crisis
        cid = f'sc-{uuid.uuid4().hex[:8]}'
        db_session.add(Crisis(id=cid, type='conflict', title='Montgomery Co. considers fire hoods', country='Testland', latitude=1.0, longitude=1.0,
                              scope='global', scope_basis=json.dumps({'v': 1, 'rule': 'no match, default', 'global': [], 'local': []}),
                              source='GDELT', date_start=datetime.utcnow(), location_confidence=55))
        db_session.commit()
        db_session.query(Crisis).filter(Crisis.id != cid).update({'scope_basis': '{"v":' + str(scope.terms_version()) + ',"rule":"x"}'}, synchronize_session=False)
        db_session.commit()
        assert scope.judge_missing() == (1, 1)
        db_session.expire_all()
        row = db_session.get(Crisis, cid)
        assert row.scope == 'local' and json.loads(row.scope_basis)['v'] == scope.terms_version()
