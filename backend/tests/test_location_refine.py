"""Refining a GDELT event's pin from its article: the country checks, every
outcome of a single refinement, the background batch, protection from the
hourly sync, and the premium endpoint. The page fetch, the AI and Nominatim
are always mocked."""
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import jwt
import pytest

import data_sources
from cache import cache_delete
from extensions import limiter
from models import Crisis, Session
from services import entitlements
from services import location_refine as lr
from services import story_facts as sf

PAGE = {'title': 'Fire at Westminster Abbey in London', 'description': 'Crews responded overnight.'}


@pytest.fixture(autouse=True)
def clean(app_module, db_session):
    limiter.reset()
    db_session.query(Crisis).delete()
    db_session.commit()
    lr._in_progress.clear()
    yield
    lr._in_progress.clear()


def seed(db_session, id=None, source='GDELT', country='United Kingdom', lat=54.0, lon=-2.0, severity=80,
         scope='global', active=True, refined_at=None, refined_name=None, days_old=0, source_url='https://example.com/a',
         kind='physical'):
    id = id or f'lr-{uuid.uuid4().hex[:8]}'
    db_session.add(Crisis(
        id=id, type='conflict', title='Auto title', country=country, latitude=lat, longitude=lon,
        severity=severity, source=source, source_url=source_url, scope=scope, is_active=active,
        location_confidence=70, location_refined_at=refined_at, location_refined_name=refined_name,
        event_kind=kind,
        date_start=datetime.utcnow() - timedelta(days=days_old),
    ))
    db_session.commit()
    return id


def fresh(db_session, crisis_id):
    db_session.expire_all()
    return db_session.query(Crisis).filter(Crisis.id == crisis_id).first()


class Mocks:
    """Patches the four collaborators; each can be reconfigured per test."""

    def __init__(self):
        self.page = PAGE
        self.place = ('Westminster Abbey, London', False)   # (name, failed)
        self.geocode = ({'lat': 51.4994, 'lon': -0.1273, 'country': 'United Kingdom'}, False)
        self.ai_available = True
        self.calls = {'page': 0, 'ai': 0, 'geo': 0}

    def fetch(self, url):
        self.calls['page'] += 1
        return self.page

    def extract(self, text):
        self.calls['ai'] += 1
        name, failed = self.place
        if failed:
            return None, True
        facts = {'place': name, 'country': None, 'is_statement': False, 'event_type': 'other', 'killed': None,
                 'injured': None, 'scale_cues': [], 'summary': None, 'confidence': 'medium'}
        return facts, False

    def geo(self, name):
        self.calls['geo'] += 1
        return self.geocode


@pytest.fixture()
def m():
    mocks = Mocks()
    with patch.object(sf, 'fetch_real_page_metadata', side_effect=mocks.fetch), \
            patch.object(sf, 'extract_facts', side_effect=mocks.extract), \
            patch.object(sf, 'facts_available', side_effect=lambda: mocks.ai_available), \
            patch.object(lr.NominatimGeocoder, 'geocode_status', side_effect=mocks.geo), \
            patch.object(lr, 'facts_available', side_effect=lambda: mocks.ai_available):
        yield mocks


# --- country comparison ---------------------------------------------------------

class TestCountryNames:
    @pytest.mark.parametrize('a,b', [
        ('Russia', 'Russian Federation'), ('Czechia', 'Czech Republic'), ('Turkey', 'Türkiye'),
        ('Myanmar', 'Myanmar (Burma)'), ('United States', 'United States of America'),
        ('United Kingdom', 'UK'), ('South Korea', 'Korea, South'), ('Palestine', 'Palestinian Territories'),
        ('Ivory Coast', "Côte d'Ivoire"), ('Bahamas', 'The Bahamas'), ('  france ', 'France'),
        ('The Gambia', 'Gambia'),
    ])
    def test_same_country_under_different_names(self, a, b):
        assert lr.same_country(a, b)

    @pytest.mark.parametrize('a,b', [
        ('France', 'Germany'), ('United States', 'Mexico'), ('Congo (Kinshasa)', 'Congo (Brazzaville)'),
        ('Sudan', 'South Sudan'), ('Korea, South', 'Korea, North'), ('India', 'Pakistan'),
    ])
    def test_different_countries_are_not_confused(self, a, b):
        assert not lr.same_country(a, b)

    @pytest.mark.parametrize('blank', [None, '', '   ', 5])
    def test_blank_never_matches(self, blank):
        assert not lr.same_country(blank, 'France')
        assert not lr.same_country('France', blank)
        assert not lr.same_country(blank, blank)


# --- one event ------------------------------------------------------------------

class TestRefineOne:
    def test_refined_location_is_saved(self, db_session, m):
        cid = seed(db_session)
        result = lr.refine_crisis_location(cid)
        assert result == {'status': 'refined', 'location': {
            'lat': 51.4994, 'lon': -0.1273, 'name': 'Westminster Abbey, London', 'country': 'United Kingdom'}}
        row = fresh(db_session, cid)
        assert (row.latitude, row.longitude) == (51.4994, -0.1273)
        assert row.location_confidence == 90
        assert row.location_refined_name == 'Westminster Abbey, London'
        assert row.location_refined_at is not None
        assert row.country == 'United Kingdom'

    def test_accepts_the_same_country_under_another_name(self, db_session, m):
        cid = seed(db_session, country='Russia')
        m.geocode = ({'lat': 55.75, 'lon': 37.62, 'country': 'Russian Federation'}, False)
        assert lr.refine_crisis_location(cid)['status'] == 'refined'

    def test_clears_the_events_cache_when_a_pin_moves(self, db_session, m):
        cid = seed(db_session)
        with patch.object(lr, 'cache_clear_prefix') as clear:
            lr.refine_crisis_location(cid)
        clear.assert_called_once_with('crises:')

    def test_unknown_event(self, m):
        assert lr.refine_crisis_location('nope') == {'status': 'not_found'}

    def test_other_sources_are_left_alone(self, db_session, m):
        cid = seed(db_session, source='NewsAPI')
        assert lr.refine_crisis_location(cid)['status'] == 'none'
        assert m.calls == {'page': 0, 'ai': 0, 'geo': 0}
        assert fresh(db_session, cid).location_refined_at is None

    def test_already_refined_returns_the_saved_result_without_any_call(self, db_session, m):
        cid = seed(db_session, lat=51.0, lon=-0.1, refined_at=datetime.utcnow(), refined_name='Somewhere')
        result = lr.refine_crisis_location(cid)
        assert result['status'] == 'refined' and result['location']['name'] == 'Somewhere'
        assert m.calls == {'page': 0, 'ai': 0, 'geo': 0}

    def test_already_tried_with_no_result_is_never_retried(self, db_session, m):
        cid = seed(db_session, refined_at=datetime.utcnow())
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        assert m.calls == {'page': 0, 'ai': 0, 'geo': 0}

    def test_second_call_after_success_makes_no_calls(self, db_session, m):
        cid = seed(db_session)
        lr.refine_crisis_location(cid)
        before = dict(m.calls)
        assert lr.refine_crisis_location(cid)['status'] == 'refined'
        assert m.calls == before

    def test_not_configured_is_unavailable_and_not_recorded(self, db_session, m):
        cid = seed(db_session)
        m.ai_available = False
        assert lr.refine_crisis_location(cid) == {'status': 'unavailable', 'reason': 'ai_not_configured'}
        assert fresh(db_session, cid).location_refined_at is None
        assert m.calls['page'] == 0

    @pytest.mark.parametrize('page', [None, {'title': None, 'description': None}, {}])
    def test_dead_or_empty_page_is_a_definite_none(self, db_session, m, page):
        cid = seed(db_session)
        m.page = page
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        row = fresh(db_session, cid)
        assert row.location_refined_at is not None and row.location_refined_name is None
        assert (row.latitude, row.longitude) == (54.0, -2.0)
        assert m.calls['ai'] == 0

    def test_event_without_a_url_is_a_definite_none(self, db_session, m):
        cid = seed(db_session, source_url=None)
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        assert m.calls['page'] == 0

    def test_model_finding_nothing_is_a_definite_none(self, db_session, m):
        cid = seed(db_session)
        m.place = (None, False)
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        assert fresh(db_session, cid).location_refined_at is not None
        assert m.calls['geo'] == 0

    def test_model_outage_is_unavailable_and_retried_later(self, db_session, m):
        cid = seed(db_session)
        m.place = (None, True)
        assert lr.refine_crisis_location(cid)['status'] == 'unavailable'
        assert fresh(db_session, cid).location_refined_at is None

    def test_a_place_that_is_just_the_country_is_no_improvement(self, db_session, m):
        cid = seed(db_session)
        m.place = ('United Kingdom', False)
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        assert m.calls['geo'] == 0
        assert fresh(db_session, cid).location_refined_at is not None

    def test_geocoder_outage_is_unavailable_and_retried_later(self, db_session, m):
        cid = seed(db_session)
        m.geocode = (None, True)
        assert lr.refine_crisis_location(cid)['status'] == 'unavailable'
        assert fresh(db_session, cid).location_refined_at is None

    def test_no_geocoder_match_is_a_definite_none(self, db_session, m):
        cid = seed(db_session)
        m.geocode = (None, False)
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        assert fresh(db_session, cid).location_refined_at is not None

    @pytest.mark.parametrize('country', ['France', None, ''])
    def test_wrong_or_missing_country_is_rejected(self, db_session, m, country):
        cid = seed(db_session)
        m.geocode = ({'lat': 48.85, 'lon': 2.35, 'country': country}, False)
        assert lr.refine_crisis_location(cid) == {'status': 'none'}
        row = fresh(db_session, cid)
        assert (row.latitude, row.longitude, row.country) == (54.0, -2.0, 'United Kingdom')
        assert row.location_refined_at is not None and row.location_refined_name is None

    def test_overlong_names_are_trimmed_to_fit_the_column(self, db_session, m):
        cid = seed(db_session)
        m.place = ('x' * 400, False)
        assert lr.refine_crisis_location(cid)['status'] == 'refined'
        assert len(fresh(db_session, cid).location_refined_name) == 200

    def test_a_second_caller_for_the_same_event_is_told_to_retry(self, db_session, m):
        cid = seed(db_session)
        lr._in_progress.add(cid)
        assert lr.refine_crisis_location(cid) == {'status': 'unavailable', 'reason': 'in_progress'}
        assert m.calls == {'page': 0, 'ai': 0, 'geo': 0}

    def test_the_in_progress_marker_is_released_even_on_error(self, db_session, m):
        cid = seed(db_session)
        with patch.object(sf, 'fetch_real_page_metadata', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                lr.refine_crisis_location(cid)
        assert cid not in lr._in_progress


# --- background batch -------------------------------------------------------------

class TestRefinePending:
    def run(self, **kwargs):
        order = []
        statuses = kwargs.pop('statuses', None)

        def fake(crisis_id):
            order.append(crisis_id)
            status = statuses[len(order) - 1] if statuses else 'none'
            return {'status': status}

        with patch.object(lr, 'refine_crisis_location', side_effect=fake):
            summary = lr.refine_pending(**kwargs)
        return summary, order

    def test_every_unrefined_physical_gdelt_event_in_worst_first_order(self, db_session):
        a = seed(db_session, severity=80)
        b = seed(db_session, severity=100)
        c = seed(db_session, severity=90)
        low = seed(db_session, severity=20)                             # no longer limited to Major
        seed(db_session, kind='statement')                              # no physical site to find
        seed(db_session, kind=None)                                     # unknown kind
        seed(db_session, scope='local')                                 # local
        seed(db_session, active=False)                                  # archived
        seed(db_session, source='NewsAPI')                              # other source
        seed(db_session, refined_at=datetime.utcnow())                  # already done
        summary, order = self.run(limit=10)
        assert sorted(order) == sorted([a, b, c, low])
        assert summary['attempted'] == 4 and summary['none'] == 4

    def test_newest_first_among_equal_source_counts(self, db_session):
        old = seed(db_session, days_old=3)
        new = seed(db_session, days_old=0)
        _, order = self.run(limit=10)
        assert order == [new, old]

    def test_stories_with_more_sources_go_first(self, db_session):
        single = seed(db_session, days_old=0)
        many = seed(db_session, days_old=5)
        db_session.query(Crisis).filter(Crisis.id == many).update({'source_count': 4})
        db_session.commit()
        _, order = self.run(limit=10)
        assert order == [many, single]

    def test_limit_is_respected(self, db_session):
        for _ in range(5):
            seed(db_session)
        _, order = self.run(limit=2)
        assert len(order) == 2

    def test_outcomes_are_counted(self, db_session):
        for _ in range(3):
            seed(db_session)
        summary, _ = self.run(limit=10, statuses=['refined', 'none', 'refined'])
        assert (summary['refined'], summary['none'], summary['unavailable']) == (2, 1, 0)

    @pytest.mark.parametrize('limit', [0, -5])
    def test_a_zero_limit_disables_it(self, db_session, limit):
        seed(db_session)
        summary, order = self.run(limit=limit)
        assert order == [] and summary['stopped'] == 'disabled'

    def test_limit_comes_from_the_environment(self, db_session, monkeypatch):
        for _ in range(4):
            seed(db_session)
        monkeypatch.setenv('LOCATION_REFINE_PER_RUN', '3')
        assert len(self.run()[1]) == 3
        monkeypatch.setenv('LOCATION_REFINE_PER_RUN', '0')
        assert self.run()[0]['stopped'] == 'disabled'
        monkeypatch.setenv('LOCATION_REFINE_PER_RUN', 'lots')
        assert lr.per_run_limit() == lr.DEFAULT_PER_RUN

    def test_stops_after_three_unavailable_in_a_row(self, db_session):
        for _ in range(8):
            seed(db_session)
        summary, order = self.run(limit=10, statuses=['unavailable'] * 8)
        assert len(order) == 3 and summary['stopped'] == 'unavailable' and summary['unavailable'] == 3

    def test_a_success_resets_the_unavailable_count(self, db_session):
        for _ in range(6):
            seed(db_session)
        summary, order = self.run(limit=10, statuses=['unavailable', 'unavailable', 'refined',
                                                      'unavailable', 'unavailable', 'none'])
        assert len(order) == 6 and summary['stopped'] is None

    def test_stops_when_the_time_budget_is_spent(self, db_session):
        seed(db_session)
        with patch.object(lr, 'RUN_TIME_BUDGET_SECONDS', -1):
            summary, order = self.run(limit=10)
        assert order == [] and summary['stopped'] == 'time_budget'

    def test_never_raises(self, db_session):
        with patch.object(lr, 'Session', side_effect=RuntimeError('db down')):
            assert lr.refine_pending(limit=5)['stopped'] == 'error'

    def test_nothing_to_do(self, db_session):
        summary, order = self.run(limit=10)
        assert order == [] and summary['attempted'] == 0


class TestStatements:
    def test_a_statement_is_never_refined_or_recorded(self, db_session, m):
        cid = seed(db_session, kind='statement')
        assert lr.refine_crisis_location(cid) == {'status': 'none', 'reason': 'statement'}
        assert m.calls == {'page': 0, 'ai': 0, 'geo': 0}
        assert fresh(db_session, cid).location_refined_at is None

    def test_an_event_of_unknown_kind_is_still_refined_on_demand(self, db_session, m):
        cid = seed(db_session, kind=None)
        assert lr.refine_crisis_location(cid)['status'] == 'refined'


# --- the hourly sync must not undo a refinement ------------------------------------------

class TestSyncKeepsRefinedPins:
    def feed(self, id, **extra):
        return {'id': id, 'type': 'conflict', 'title': 'Feed title', 'country': 'United Kingdom',
                'latitude': 54.0, 'longitude': -2.0, 'severity': 95, 'location_confidence': 70, **extra}

    def test_refined_location_survives_a_re_ingest_but_other_fields_update(self, db_session):
        cid = seed(db_session, lat=51.4994, lon=-0.1273, refined_at=datetime.utcnow(), refined_name='Abbey',
                   severity=60)
        row = db_session.query(Crisis).filter(Crisis.id == cid).first()
        row.location_confidence = 90
        db_session.commit()

        session = Session()
        data_sources.DataAggregator._upsert_crisis(session, self.feed(cid))
        session.commit()
        session.close()

        row = fresh(db_session, cid)
        assert (row.latitude, row.longitude, row.location_confidence) == (51.4994, -0.1273, 90)
        assert row.severity == 95 and row.title == 'Feed title'

    def test_an_unrefined_row_is_still_fully_updated(self, db_session):
        cid = seed(db_session, lat=10.0, lon=10.0)
        session = Session()
        data_sources.DataAggregator._upsert_crisis(session, self.feed(cid))
        session.commit()
        session.close()
        row = fresh(db_session, cid)
        assert (row.latitude, row.longitude) == (54.0, -2.0)


# --- API fields --------------------------------------------------------------------------

def test_to_dict_exposes_the_refinement_fields(db_session):
    cid = seed(db_session, refined_at=datetime(2026, 10, 4, 12, 0), refined_name='Abbey')
    body = fresh(db_session, cid).to_dict()
    assert body['location_refined_name'] == 'Abbey'
    assert body['location_refined_at'] == '2026-10-04T12:00:00'
    plain = fresh(db_session, seed(db_session)).to_dict()
    assert plain['location_refined_name'] is None and plain['location_refined_at'] is None


def test_real_headline_no_longer_changes_locations(client, db_session):
    cid = seed(db_session)
    with patch('blueprints.crises.fetch_real_page_metadata', return_value={'title': 'Real', 'description': 'd'}):
        body = client.get(f'/api/crises/{cid}/real-headline').get_json()
    assert body['title'] == 'Real' and body['location'] is None
    row = fresh(db_session, cid)
    assert (row.latitude, row.longitude) == (54.0, -2.0) and row.location_refined_at is None


# --- endpoint ------------------------------------------------------------------------------

SECRET = 'jwt-signing-secret'


def token(user_id):
    return jwt.encode({'sub': user_id, 'aud': 'authenticated', 'exp': int(time.time()) + 3600},
                      SECRET, algorithm='HS256')


def call(client, crisis_id, user=None, plan='active'):
    headers = {}
    if user:
        headers['Authorization'] = f'Bearer {token(user)}'
        cache_delete(f'plan:{user}')
    with patch.object(entitlements, '_fetch_subscription', return_value={'status': plan} if plan else None):
        return client.post(f'/api/crises/{crisis_id}/refine-location', headers=headers)


class TestEndpoint:
    @pytest.fixture(autouse=True)
    def secret(self, monkeypatch):
        monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)

    def test_anonymous_is_401_and_nothing_runs(self, client):
        with patch('blueprints.crises.refine_crisis_location') as refine:
            assert call(client, 'x').status_code == 401
        refine.assert_not_called()

    def test_free_member_is_403_and_nothing_runs(self, client):
        with patch('blueprints.crises.refine_crisis_location') as refine:
            res = call(client, 'x', str(uuid.uuid4()), plan=None)
        assert res.status_code == 403 and res.get_json()['error'] == 'premium_required'
        refine.assert_not_called()

    def test_premium_gets_the_result(self, client):
        result = {'status': 'refined', 'location': {'lat': 1.0, 'lon': 2.0, 'name': 'Abbey', 'country': 'UK'}}
        with patch('blueprints.crises.refine_crisis_location', return_value=result) as refine:
            res = call(client, 'abc', str(uuid.uuid4()))
        assert res.status_code == 200 and res.get_json() == result
        refine.assert_called_once_with('abc')

    def test_none_is_a_normal_answer(self, client):
        with patch('blueprints.crises.refine_crisis_location', return_value={'status': 'none'}):
            res = call(client, 'abc', str(uuid.uuid4()))
        assert res.status_code == 200 and res.get_json() == {'status': 'none'}

    def test_unknown_event_is_404(self, client):
        with patch('blueprints.crises.refine_crisis_location', return_value={'status': 'not_found'}):
            assert call(client, 'abc', str(uuid.uuid4())).status_code == 404

    def test_unavailable_is_503_with_a_reason(self, client):
        with patch('blueprints.crises.refine_crisis_location',
                   return_value={'status': 'unavailable', 'reason': 'ai_not_configured'}):
            res = call(client, 'abc', str(uuid.uuid4()))
        assert res.status_code == 503
        assert res.get_json() == {'error': 'location_refinement_unavailable', 'reason': 'ai_not_configured'}

    def test_unexpected_errors_are_a_generic_500(self, client):
        with patch('blueprints.crises.refine_crisis_location', side_effect=RuntimeError('boom')):
            res = call(client, 'abc', str(uuid.uuid4()))
        assert res.status_code == 500 and 'boom' not in res.get_data(as_text=True)

    def test_end_to_end_with_the_real_service(self, client, db_session, m):
        cid = seed(db_session)
        res = call(client, cid, str(uuid.uuid4()))
        assert res.status_code == 200 and res.get_json()['status'] == 'refined'
        assert fresh(db_session, cid).location_refined_name == 'Westminster Abbey, London'

    def test_rate_limited_after_20_a_minute(self, client):
        user = str(uuid.uuid4())
        with patch('blueprints.crises.refine_crisis_location', return_value={'status': 'none'}):
            codes = [call(client, 'abc', user).status_code for _ in range(21)]
        assert codes[:20] == [200] * 20 and codes[20] == 429
