"""
Tests for fetch_real_page_metadata() (data_sources) and
GET /api/crises/<id>/real-headline — the lazy real-headline fetch for
crises whose stored title is auto-generated.

Pin-location refinement used to live in this endpoint; it is now its own
service (services/location_refine.py, tests in test_location_refine.py).
"""
from unittest.mock import patch, MagicMock

import pytest

import data_sources as ds
from models import Crisis


@pytest.fixture(autouse=True)
def clean_crises(db_session):
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(Crisis).delete()
    db_session.commit()


def seed_crisis(db_session, id='rh-1', source='GDELT', source_url='https://example.com/real-article',
                 latitude=1.0, longitude=1.0, country='Testland'):
    db_session.add(Crisis(
        id=id, type='conflict', title='Auto-generated title', country=country,
        latitude=latitude, longitude=longitude, severity=70, source=source, source_url=source_url,
    ))
    db_session.commit()


def _html_response(title_html=None, description_html=None, image_url=None, video_url=None):
    resp = MagicMock()
    head = ''
    if title_html is not None:
        head += f"<title>{title_html}</title>"
    if description_html is not None:
        head += f'<meta name="description" content="{description_html}">'
    if image_url is not None:
        head += f'<meta property="og:image" content="{image_url}">'
    if video_url is not None:
        head += f'<meta property="og:video" content="{video_url}">'
    resp.text = f"<html><head>{head}</head><body></body></html>"
    resp.raise_for_status = lambda: None
    return resp


# ── fetch_real_page_metadata() ────────────────────────────────────────────

def test_extracts_real_title_and_description(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response('Real Headline', 'A real summary')):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result == {'title': 'Real Headline', 'description': 'A real summary', 'image_url': None, 'video_url': None, 'excerpt': None}


def test_extracts_og_image_and_video(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response(
        'Real Headline', 'A real summary',
        image_url='https://example.com/photo.jpg', video_url='https://example.com/clip.mp4',
    )):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result['image_url'] == 'https://example.com/photo.jpg'
    assert result['video_url'] == 'https://example.com/clip.mp4'


def test_og_image_absent_when_no_meta_tag(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response('Real Headline')):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result['image_url'] is None
    assert result['video_url'] is None


def test_og_image_reverse_attribute_order(app_module):
    resp = MagicMock()
    resp.text = (
        '<html><head><title>T</title>'
        '<meta content="https://example.com/rev.jpg" property="og:image">'
        '</head><body></body></html>'
    )
    resp.raise_for_status = lambda: None
    with patch('data_sources.utils.requests.get', return_value=resp):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result['image_url'] == 'https://example.com/rev.jpg'


def test_og_image_rejects_non_http_url():
    from data_sources.utils import fetch_real_page_metadata as frpm
    resp = MagicMock()
    resp.text = (
        '<html><head><title>T</title>'
        '<meta property="og:image" content="javascript:alert(1)">'
        '</head><body></body></html>'
    )
    resp.raise_for_status = lambda: None
    with patch('data_sources.utils.requests.get', return_value=resp):
        result = frpm('https://example.com/a')
    assert result['image_url'] is None


def test_decodes_html_entities(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response('Tensions &amp; Talks Rise')):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result['title'] == 'Tensions & Talks Rise'


def test_collapses_whitespace(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response('Real\n   Headline\t Here')):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result['title'] == 'Real Headline Here'


def test_missing_title_but_present_description_is_not_none(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response(None, 'Only a description')):
        result = ds.fetch_real_page_metadata('https://example.com/a')
    assert result == {'title': None, 'description': 'Only a description', 'image_url': None, 'video_url': None, 'excerpt': None}


def test_returns_none_when_page_has_neither_title_nor_description(app_module):
    resp = MagicMock()
    resp.text = "<html><head></head><body>Nothing useful</body></html>"
    resp.raise_for_status = lambda: None
    with patch('data_sources.utils.requests.get', return_value=resp):
        assert ds.fetch_real_page_metadata('https://example.com/a') is None


def test_returns_none_on_network_failure(app_module):
    with patch('data_sources.utils.requests.get', side_effect=Exception('network down')):
        assert ds.fetch_real_page_metadata('https://example.com/a') is None


def test_rejects_non_http_url(app_module):
    assert ds.fetch_real_page_metadata('javascript:alert(1)') is None
    assert ds.fetch_real_page_metadata('') is None
    assert ds.fetch_real_page_metadata(None) is None


def test_sends_a_descriptive_user_agent(app_module):
    with patch('data_sources.utils.requests.get', return_value=_html_response('X')) as mock_get:
        ds.fetch_real_page_metadata('https://example.com/a')
        headers = mock_get.call_args.kwargs.get('headers', {})
        assert headers.get('User-Agent')


# ── GET /api/crises/<id>/real-headline ───────────────────────────────────
# Each test uses its own crisis id — the endpoint's cache key is derived
# from crisis_id and persists in the shared in-memory cache for the whole
# test session, so reusing one id across tests would leak a cached result.

def test_endpoint_returns_real_title(client, db_session):
    seed_crisis(db_session, id='rh-returns-title')
    with patch('blueprints.crises.fetch_real_page_metadata', return_value={'title': 'The Real Headline', 'description': None}):
        resp = client.get('/api/crises/rh-returns-title/real-headline')
    assert resp.status_code == 200
    assert resp.get_json()['title'] == 'The Real Headline'


def test_endpoint_returns_none_title_when_no_source_url(client, db_session):
    seed_crisis(db_session, id='rh-no-url', source_url=None)
    resp = client.get('/api/crises/rh-no-url/real-headline')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['title'] is None
    assert body['location'] is None


def test_endpoint_404s_for_missing_crisis(client, db_session):
    resp = client.get('/api/crises/does-not-exist/real-headline')
    assert resp.status_code == 404


def test_endpoint_caches_result_and_does_not_refetch(client, db_session):
    seed_crisis(db_session, id='rh-cached')
    with patch('blueprints.crises.fetch_real_page_metadata',
               return_value={'title': 'Cached Headline', 'description': None}) as mock_fetch:
        client.get('/api/crises/rh-cached/real-headline')
        client.get('/api/crises/rh-cached/real-headline')
    assert mock_fetch.call_count == 1
