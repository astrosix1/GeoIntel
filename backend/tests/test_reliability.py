"""
Tests for `_reliability_from_news()` in app.py — the shared scoring logic
behind both GET /api/crises/<id>/reliability and the batched version used
by GET /api/crises?include_analysis=true. Only `.source` is read off each
article, so plain objects stand in for News rows here.
"""
from types import SimpleNamespace


def article(source):
    return SimpleNamespace(source=source)


def test_source_reliability_table_loaded_from_config(app_module):
    # SOURCE_RELIABILITY is read from config/source_reliability.json at
    # import time — this catches a broken path/JSON syntax error silently
    # degrading every score to DEFAULT_SOURCE_SCORE (see _load_source_reliability).
    assert app_module.SOURCE_RELIABILITY.get('Reuters') == 95
    assert '_comment' not in app_module.SOURCE_RELIABILITY


def test_no_articles_is_unknown(app_module):
    result = app_module._reliability_from_news([])
    assert result['reliability'] == 'unknown'
    assert result['source_count'] == 0


def test_three_plus_high_trust_sources_is_verified(app_module):
    articles = [article('Reuters'), article('AP'), article('BBC')]
    result = app_module._reliability_from_news(articles)
    assert result['reliability'] == 'verified'
    assert result['source_count'] == 3


def test_two_solid_sources_is_corroborated(app_module):
    articles = [article('BBC'), article('CNN')]
    result = app_module._reliability_from_news(articles)
    assert result['reliability'] == 'corroborated'


def test_single_moderate_source_is_reported(app_module):
    articles = [article('NewsAPI')]
    result = app_module._reliability_from_news(articles)
    assert result['reliability'] == 'reported'


def test_single_low_trust_source_is_unverified(app_module):
    articles = [article('Activistpost.com')]
    result = app_module._reliability_from_news(articles)
    assert result['reliability'] == 'unverified'


def test_unknown_source_defaults_to_moderate_score(app_module):
    # A source not in SOURCE_RELIABILITY should score 65, not crash.
    articles = [article('Some New Outlet Nobody Has Seen Before')]
    result = app_module._reliability_from_news(articles)
    assert result['score'] == 65


def test_duplicate_sources_only_count_once(app_module):
    articles = [article('Reuters'), article('Reuters'), article('Reuters')]
    result = app_module._reliability_from_news(articles)
    assert result['source_count'] == 1
    # 3 corroborating articles from ONE outlet should not read as "verified"
    # (that requires 3+ distinct sources), even though the single-source
    # score is high.
    assert result['reliability'] != 'verified'


def test_missing_source_field_falls_back_to_unknown_label(app_module):
    articles = [article(None)]
    result = app_module._reliability_from_news(articles)
    assert result['sources'] == ['Unknown']
