"""The strict severity scale, row by row."""
import json
import uuid

import pytest

from models import Crisis
from services import severity as sev


def facts(**extra):
    base = {'place': None, 'country': None, 'is_statement': False, 'event_type': 'other', 'killed': None,
            'injured': None, 'scale_cues': [], 'summary': None, 'confidence': 'high'}
    return {**base, **extra}


class TestLevels:
    @pytest.mark.parametrize('score,level,name', [
        (0, 1, 'Minor'), (19, 1, 'Minor'), (20, 2, 'Moderate'), (39, 2, 'Moderate'), (40, 3, 'Serious'),
        (59, 3, 'Serious'), (60, 4, 'Severe'), (79, 4, 'Severe'), (80, 5, 'Critical'), (100, 5, 'Critical'),
    ])
    def test_bands(self, score, level, name):
        assert sev.level_of(score) == (level, name)


class TestHeadlineOnly:
    def test_is_capped_at_serious_and_says_so(self):
        result = sev.score_story(100, 'physical', None, 1)
        assert result['score'] <= 59 and result['level'] <= 3
        assert any('Headline-only' in b for b in result['basis'])

    def test_even_many_outlets_stay_capped(self):
        assert sev.score_story(100, 'physical', None, 20)['score'] == 59

    def test_scales_with_feed_intensity(self):
        assert sev.score_story(0, 'physical', None, 1)['score'] < sev.score_story(80, 'physical', None, 1)['score']


class TestStatements:
    def test_capped_below_serious_top(self):
        assert sev.score_story(100, 'statement', None, 9)['score'] <= 49
        assert sev.score_story(100, 'physical', facts(is_statement=True, killed=50), 9)['score'] <= 49


class TestFacts:
    @pytest.mark.parametrize('killed,minimum', [(1, 55), (2, 55), (3, 65), (9, 65), (10, 79), (99, 79), (100, 79)])
    def test_deaths_set_a_floor_single_outlet(self, killed, minimum):
        result = sev.score_story(0, 'physical', facts(killed=killed), 1)
        assert result['score'] >= minimum

    def test_ten_killed_is_critical_with_two_outlets(self):
        result = sev.score_story(0, 'physical', facts(killed=10), 2)
        assert result['level'] == 5 and any('10 killed' in b for b in result['basis'])

    def test_critical_needs_two_outlets(self):
        result = sev.score_story(0, 'physical', facts(killed=500, scale_cues=['mass_casualty']), 1)
        assert result['score'] == 79 and result['level'] == 4
        assert any('two or more' in b for b in result['basis'])

    def test_mass_casualty_cue_floors_high(self):
        assert sev.score_story(0, 'physical', facts(scale_cues=['chemical_bio_nuclear']), 3)['level'] == 5

    def test_injuries_alone_floor(self):
        assert sev.score_story(0, 'physical', facts(injured=12), 1)['score'] >= 45

    def test_no_stated_casualties_stays_low(self):
        assert sev.score_story(100, 'physical', facts(event_type='crime'), 1)['level'] <= 2

    def test_corroboration_adds_at_most_ten(self):
        one = sev.score_story(0, 'physical', facts(event_type='armed_conflict'), 1)['score']
        many = sev.score_story(0, 'physical', facts(event_type='armed_conflict'), 50)['score']
        assert many - one == 10

    def test_basis_is_stated_not_invented(self):
        result = sev.score_story(0, 'physical', facts(killed=5), 4)
        assert 'Reported by 4 outlets' in result['basis'] and '5 killed, stated in the article' in result['basis']

    def test_bad_inputs_do_not_crash(self):
        assert 0 <= sev.score_story(None, None, facts(killed=None), 0)['score'] <= 100


def seed(db_session, **extra):
    cid = f'sv-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(id=cid, type='conflict', title='t', country='X', latitude=1, longitude=1, severity=100,
                          source='GDELT', is_active=True, event_kind='physical', **extra))
    db_session.commit()
    return cid


class TestStored:
    def test_rescore_is_idempotent_and_keeps_the_feed_value(self, app_module, db_session):
        row = db_session.query(Crisis).filter(Crisis.id == seed(db_session)).first()
        first = sev.rescore(row)
        second = sev.rescore(row)
        assert first['score'] == second['score'] <= 59
        assert json.loads(row.severity_basis)['feed'] == 100 and row.severity_level == first['level']

    def test_other_sources_keep_their_own_severity(self, app_module, db_session):
        row = db_session.query(Crisis).filter(Crisis.id == seed(db_session)).first()
        row.source = 'ACLED'
        assert sev.rescore(row) is None and row.severity == 100

    def test_a_new_gdelt_row_is_scored_on_ingest(self, app_module, db_session):
        from data_sources import DataAggregator
        cid = f'sv-{uuid.uuid4().hex[:8]}'
        data = dict(id=cid, type='conflict', title='t', country='X', latitude=1, longitude=1, severity=100,
                    source='GDELT', is_active=True, event_kind='physical')
        DataAggregator._upsert_crisis(db_session, data)
        db_session.commit()
        row = db_session.query(Crisis).filter(Crisis.id == cid).first()
        assert row.severity <= 59 and row.severity_basis
        DataAggregator._upsert_crisis(db_session, {**data, 'severity': 100})   # feed re-sync
        db_session.commit()
        db_session.expire_all()
        assert db_session.query(Crisis).filter(Crisis.id == cid).first().severity <= 59
