"""
Tests for the event pipeline scaffolding (event_pipeline/): stable news ids,
URL canonicalization, candidate normalization, the PipelineReport, and the
sync paths (primary + multilingual) that now route every candidate through
process_batch before upsert.
"""
import math
from unittest.mock import patch

import pytest

import data_sources as ds
import event_pipeline
from event_pipeline.normalize import canonical_url, stable_news_id, normalize_candidate
from models import Crisis


def make_candidate(**overrides):
    base = {
        'id': 'test_1',
        'type': 'conflict',
        'title': 'Armed clash near Kharkiv',
        'country': 'Ukraine',
        'latitude': 49.99,
        'longitude': 36.23,
        'severity': 60,
        'confidence': 70,
        'location_confidence': 82,
        'source': 'NewsAPI',
    }
    base.update(overrides)
    return base


@pytest.fixture()
def clean_crises(db_session):
    db_session.query(Crisis).filter(Crisis.id.like('news_%') | Crisis.id.like('test_%')).delete(
        synchronize_session=False)
    db_session.commit()
    yield
    db_session.query(Crisis).filter(Crisis.id.like('news_%') | Crisis.id.like('test_%')).delete(
        synchronize_session=False)
    db_session.commit()


# ── canonical URLs + stable ids ────────────────────────────────────────────

def test_canonical_url_strips_tracking_www_amp_fragment_and_slash():
    a = canonical_url('https://www.Reuters.com/world/story-123/?utm_source=x&fbclid=y#top')
    b = canonical_url('https://reuters.com/world/story-123')
    c = canonical_url('https://reuters.com/world/story-123/amp')
    assert a == b == c


def test_canonical_url_keeps_meaningful_query_params():
    assert canonical_url('https://site.com/a?id=5') != canonical_url('https://site.com/a?id=6')


def test_stable_news_id_is_deterministic_and_distinct_per_article():
    one = stable_news_id('https://reuters.com/a')
    assert one == stable_news_id('https://www.reuters.com/a/?utm_medium=rss')
    assert one != stable_news_id('https://reuters.com/b')
    assert one.startswith('news_') and len(one) <= 50


def test_same_outlet_same_day_articles_no_longer_collide(app_module):
    # The old id was news_{source}_{date}: both of these got the same id.
    def article(url, title):
        return {'title': title, 'description': 'Troops and armed forces clashed.',
                'source': {'name': 'Reuters'}, 'publishedAt': '2026-09-20T10:00:00Z', 'url': url}
    first = ds.NewsBasedCrisisDetector._extract_crisis_from_article(
        article('https://reuters.com/a', 'Armed clash near Kharkiv'))
    second = ds.NewsBasedCrisisDetector._extract_crisis_from_article(
        article('https://reuters.com/b', 'Missile strike on Odesa port'))
    assert first['id'] != second['id']


# ── normalize_candidate ────────────────────────────────────────────────────

def test_normalize_accepts_and_clamps_a_valid_candidate():
    c = make_candidate(title='x ' * 300, severity=140, source_id='u' * 400, id='i' * 80)
    assert normalize_candidate(c) is None
    assert len(c['title']) <= 200 and c['title'].endswith('…')
    assert c['severity'] == 100
    assert len(c['source_id']) == 100
    assert len(c['id']) == 50


@pytest.mark.parametrize('lat,lon', [(0, 0), (91, 10), (10, -181), (math.nan, 5), ('abc', 5)])
def test_normalize_rejects_invalid_coordinates(lat, lon):
    assert normalize_candidate(make_candidate(latitude=lat, longitude=lon)) == 'invalid_coordinates'


@pytest.mark.parametrize('field', ['id', 'type', 'country', 'latitude'])
def test_normalize_rejects_missing_required_fields(field):
    assert normalize_candidate(make_candidate(**{field: None})) == 'missing_fields'


# ── process_batch + report ─────────────────────────────────────────────────

def test_process_batch_keeps_valid_rejects_invalid_and_dedups_ids():
    candidates = [
        make_candidate(id='a'),
        make_candidate(id='a', title='Same id with a different headline'),
        make_candidate(id='b', latitude=0, longitude=0),
        make_candidate(id='c', title=''),
        make_candidate(id='d', title='Protesters rally against conscription in Lviv', type='civil_unrest',
                       latitude=49.84, longitude=24.03, _meta={'raw': 'transient'}),
    ]
    result = event_pipeline.process_batch(candidates, 'NewsAPI')

    assert [c['id'] for c in result.kept] == ['a', 'd']
    assert '_meta' not in result.kept[1]
    reasons = sorted(reason for reason, _ in result.rejected)
    assert reasons == ['duplicate_in_batch', 'invalid_coordinates', 'no_usable_title']

    summary = result.report.to_dict()
    assert summary['totals'] == {'received': 5, 'kept': 2, 'merged': 0, 'rejected': 3}
    assert summary['sources']['NewsAPI']['rejected']['invalid_coordinates'] == 1
    assert summary['sources']['NewsAPI']['severity_bands'] == {'high': 2}


def test_report_merges_multiple_sources_into_one_summary():
    report = event_pipeline.PipelineReport(label='sync')
    event_pipeline.process_batch([make_candidate(id='x')], 'ACLED', report=report)
    event_pipeline.process_batch([make_candidate(id='y', latitude=0, longitude=0)], 'GDELT', report=report)
    line = report.summary_line()
    assert 'ACLED: 1 in, 1 kept' in line
    assert 'GDELT: 1 in, 0 kept, 1 rejected (invalid_coordinates=1)' in line


# ── sync paths ─────────────────────────────────────────────────────────────

def test_sync_all_sources_runs_every_connector_through_the_pipeline(app_module, db_session, clean_crises):
    good = make_candidate(id='test_good', source='GDELT')
    bad = make_candidate(id='test_bad', source='GDELT', latitude=0, longitude=0)
    with patch.object(ds.ACLEDConnector, 'fetch_recent_events', return_value=[]), \
         patch.object(ds.GDELTConnector, 'fetch_recent_events', return_value=[good, bad]), \
         patch.object(ds.NewsBasedCrisisDetector, 'extract_crises_from_news', return_value=[]), \
         patch.object(ds.NewsAPIConnector, 'fetch_geopolitical_news', return_value=[]), \
         patch.object(ds.WorldBankConnector, 'fetch_country_indicators', return_value=[]):
        ds.DataAggregator.sync_all_sources()

    assert db_session.query(Crisis).filter_by(id='test_good').first() is not None
    assert db_session.query(Crisis).filter_by(id='test_bad').first() is None
    latest = event_pipeline.recent_reports()[0]
    assert latest['sources']['GDELT']['rejected'] == {'invalid_coordinates': 1}


def test_multilingual_sync_goes_through_pipeline_and_upsert(app_module, db_session, clean_crises):
    from newsapi_multilingual import MultilingualNewsConnector

    articles = [{
        'title': 'Armed clash near Kharkiv as troops advance',
        'description': 'Fighting intensified.',
        'source': {'name': 'El País'},
        'publishedAt': '2026-09-20T10:00:00Z',
        'url': 'https://elpais.com/internacional/kharkiv-clash',
    }]
    connector = MultilingualNewsConnector()
    with patch.object(connector, 'fetch_articles', return_value=articles):
        added_first = connector.sync_all_languages(db_session)
        added_again = connector.sync_all_languages(db_session)

    # The same article returned by every language query is one row, and a
    # second run updates it rather than inserting again.
    assert added_first == 1
    assert added_again == 0
    rows = db_session.query(Crisis).filter(Crisis.id.like('news_%')).all()
    assert len(rows) == 1


def test_pipeline_report_endpoint_requires_admin(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'secret-key')
    assert client.get('/api/admin/pipeline-report').status_code == 401
    ok = client.get('/api/admin/pipeline-report', headers={'X-Admin-Key': 'secret-key'})
    assert ok.status_code == 200
    assert 'reports' in ok.get_json()
