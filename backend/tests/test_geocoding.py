"""
Tests for news-article geocoding in data_sources.py.

Geocoding is rules-only: the AI (Claude) + Nominatim path was removed —
it called a retired model and so had been silently failing, with every
article falling through to the curated city match anyway. What's left is
the curated LOCATION_MAP match (title first, then description, dateline
stripped). Location validation — metonymy, ambiguous names, the
point-in-country check — is a later event_pipeline stage; see
docs/EVENT_FILTERING.md.
"""
from unittest.mock import patch

import data_sources as ds


def _article(title, description='', url='https://example.com/a'):
    return {
        'title': title,
        'description': description,
        'source': {'name': 'Test Wire'},
        'publishedAt': '2026-01-01T00:00:00Z',
        'url': url,
    }


def test_ai_geocoding_path_is_gone(app_module):
    assert not hasattr(ds, '_extract_incident_location')
    assert not hasattr(ds, 'NominatimGeocoder')
    assert not hasattr(ds, '_geocode_ai_client')


def test_extract_crisis_uses_curated_city_match_without_any_network(app_module):
    article = _article('Military conflict escalates near Tehran',
                       'Officials reported an armed clash amid rising tension.')
    with patch('data_sources.requests.get') as mock_get:
        crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article(article)
        assert mock_get.call_count == 0

    assert crisis is not None
    assert crisis['country'] == 'Iran'
    assert crisis['location_confidence'] == 82


def test_title_city_wins_over_dateline_city(app_module):
    article = _article('Armed clash reported near Khartoum',
                       'LIMA, Sept 20 (Reuters) - Fighting continued across the region.')
    crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article(article)
    assert crisis['country'] == 'Sudan'


def test_article_without_a_known_city_is_skipped(app_module):
    article = _article('Troops clash in a remote border region', 'Fighting was reported.')
    assert ds.NewsBasedCrisisDetector._extract_crisis_from_article(article) is None
