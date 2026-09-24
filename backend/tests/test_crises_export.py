"""
Tests for GET /api/crises/export (Phase 4 of the compendious-tool roadmap).

This endpoint used to be admin-key-gated even though it only re-shapes data
already public via GET /api/crises, had a documented but unimplemented
`format` query param (CSV was the only real output), and exported only 8
thin columns with none of the real Phase 1/2 trust-signal data. It's now
public (rate-limited instead), supports format=json|csv for real, supports
type/min_severity/country filters matching the frontend's own filter model,
and includes real reliability/verification/domain/stakeholder data.
"""
import csv
import io

import pytest

from models import Crisis, News


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    db_session.query(News).delete()
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(News).delete()
    db_session.query(Crisis).delete()
    db_session.commit()


def seed_crisis(db_session, id='exp-1', country='Testland', ctype='conflict', severity=70, is_verified=True, stakeholders='US,RU'):
    db_session.add(Crisis(
        id=id, type=ctype, title=f'Crisis {id}', country=country,
        latitude=0, longitude=0, severity=severity, confidence=80,
        is_verified=is_verified, stakeholders=stakeholders,
        military_score=10, economic_score=20, political_score=30,
        environment_score=0, technology_score=0, information_score=0,
    ))
    db_session.commit()


def test_export_no_longer_requires_auth(client, db_session):
    seed_crisis(db_session)
    resp = client.get('/api/crises/export')
    assert resp.status_code == 200


def test_default_format_is_csv(client, db_session):
    seed_crisis(db_session)
    resp = client.get('/api/crises/export')
    assert resp.content_type.startswith('text/csv')
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][0] == 'ID'
    assert any(r[0] == 'exp-1' for r in rows[1:])


def test_json_format_returns_real_enriched_fields(client, db_session):
    seed_crisis(db_session)
    db_session.add_all([
        News(id='n1', crisis_id='exp-1', title='A', source='Reuters'),
        News(id='n2', crisis_id='exp-1', title='B', source='AP'),
        News(id='n3', crisis_id='exp-1', title='C', source='BBC'),
    ])
    db_session.commit()

    resp = client.get('/api/crises/export?format=json')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['count'] == 1
    record = body['crises'][0]
    assert record['id'] == 'exp-1'
    assert record['is_verified'] is True
    assert record['stakeholders'] == ['US', 'RU']
    assert record['reliability'] == 'verified'  # 3 high-trust sources
    assert record['source_count'] == 3
    assert record['domains']['political'] == 30


def test_invalid_format_is_rejected(client, db_session):
    resp = client.get('/api/crises/export?format=xml')
    assert resp.status_code == 400


def test_type_filter_narrows_results(client, db_session):
    seed_crisis(db_session, id='exp-conflict', ctype='conflict')
    seed_crisis(db_session, id='exp-economic', ctype='economic')

    resp = client.get('/api/crises/export?format=json&type=economic')
    body = resp.get_json()
    ids = [c['id'] for c in body['crises']]
    assert ids == ['exp-economic']


def test_min_severity_filter_narrows_results(client, db_session):
    seed_crisis(db_session, id='exp-low', severity=20)
    seed_crisis(db_session, id='exp-high', severity=90)

    resp = client.get('/api/crises/export?format=json&min_severity=50')
    body = resp.get_json()
    ids = [c['id'] for c in body['crises']]
    assert ids == ['exp-high']


def test_country_filter_narrows_results(client, db_session):
    seed_crisis(db_session, id='exp-a', country='Alpha')
    seed_crisis(db_session, id='exp-b', country='Beta')

    resp = client.get('/api/crises/export?format=json&country=Beta')
    body = resp.get_json()
    ids = [c['id'] for c in body['crises']]
    assert ids == ['exp-b']


def test_comma_separated_type_filter_matches_frontend_domain_grouping(client, db_session):
    # The frontend's "domain" filter (e.g. Military) maps to several crisis
    # types (conflict/military/proxy) — domain itself isn't a stored column,
    # so the frontend sends a comma-separated type list instead.
    seed_crisis(db_session, id='exp-conflict', ctype='conflict')
    seed_crisis(db_session, id='exp-military', ctype='military')
    seed_crisis(db_session, id='exp-economic', ctype='economic')

    resp = client.get('/api/crises/export?format=json&type=conflict,military')
    body = resp.get_json()
    ids = sorted(c['id'] for c in body['crises'])
    assert ids == ['exp-conflict', 'exp-military']


def test_no_stakeholders_returns_empty_list_not_a_guess(client, db_session):
    seed_crisis(db_session, id='exp-nostake', stakeholders=None)
    resp = client.get('/api/crises/export?format=json')
    body = resp.get_json()
    assert body['crises'][0]['stakeholders'] == []
