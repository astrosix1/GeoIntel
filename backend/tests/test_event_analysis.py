"""The Analysis tab's pattern and related-events blocks (services/event_analysis.py)."""
from datetime import datetime, timedelta

from models import Crisis


def _add(db, cid, days_ago, country='Sudan', type_='conflict', kind='physical', lat=15.0, lon=32.0, **kw):
    db.add(Crisis(id=cid, type=type_, title=cid, country=country, latitude=lat, longitude=lon, severity=50, is_active=True,
                  event_kind=kind, date_start=datetime.utcnow() - timedelta(days=days_ago, hours=1), **kw))


def test_pattern_counts_this_week_against_the_one_before(app_module, db_session):
    from services.event_analysis import build_pattern
    for i in range(8):
        _add(db_session, f'now{i}', 1)
    for i in range(4):
        _add(db_session, f'prev{i}', 9)
    _add(db_session, 'talk', 1, kind='statement')                 # statements are not counted
    _add(db_session, 'other', 1, country='Chad', lat=15, lon=19)                  # other countries are not counted
    _add(db_session, 'cyber', 1, type_='cyber')                   # nor non-violent types
    db_session.commit()
    me = db_session.query(Crisis).filter(Crisis.id == 'now0').one()
    p = build_pattern(db_session, me)
    assert (p['last_7_days'], p['previous_7_days'], p['direction']) == (8, 4, 'rising')
    assert len(p['weekly']) == 8


def test_pattern_is_none_without_reports_and_too_few_is_not_called(app_module, db_session):
    from services.event_analysis import build_pattern
    _add(db_session, 'solo', 1, country='Norway', lat=60, lon=10)
    db_session.commit()
    me = db_session.query(Crisis).filter(Crisis.id == 'solo').one()
    assert build_pattern(db_session, me)['direction'] == 'too_few'   # nothing earlier to compare against
    _add(db_session, 'cyb', 1, country='Iceland', type_='cyber')
    db_session.commit()
    assert build_pattern(db_session, db_session.query(Crisis).filter(Crisis.id == 'cyb').one()) is None


def test_related_same_type_nearby_in_time(app_module, db_session):
    from services.event_analysis import build_related
    k = dict(country='Kenya', lat=1.0, lon=37.0)
    _add(db_session, 'me', 0, **k)
    _add(db_session, 'a', 3, **k)
    _add(db_session, 'far', 3, country='Chile', lat=-30, lon=-70)
    _add(db_session, 'old', 100, **k)
    _add(db_session, 'diff', 2, type_='cyber', **k)
    db_session.commit()
    me = db_session.query(Crisis).filter(Crisis.id == 'me').one()
    assert [r['id'] for r in build_related(db_session, me)] == ['a']


def test_endpoint(client, app_module, db_session):
    _add(db_session, 'e1', 1, country='Laos', lat=19, lon=102)
    db_session.commit()
    r = client.get('/api/crises/e1/analysis')
    assert r.status_code == 200 and r.get_json()['pattern']['last_7_days'] == 1
    assert client.get('/api/crises/nope/analysis').status_code == 404
