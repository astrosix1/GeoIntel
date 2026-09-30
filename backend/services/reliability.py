"""
Source reliability scoring.

Source reliability mapping (higher = more trustworthy) lives in
config/source_reliability.json so a new outlet can be added without a
code change; a source missing from the file scores DEFAULT_SOURCE_SCORE.
"""
import json
import logging
import os
from collections import defaultdict

from models import Session, News

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_SCORE = 65
_SOURCE_RELIABILITY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'source_reliability.json'
)


def _load_source_reliability():
    try:
        with open(_SOURCE_RELIABILITY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith('_')}
    except Exception as e:
        logger.error(f"Could not load {_SOURCE_RELIABILITY_PATH}: {e}. Using empty source reliability table (every source will score {DEFAULT_SOURCE_SCORE}).")
        return {}


SOURCE_RELIABILITY = _load_source_reliability()


def calculate_source_reliability(crisis_id):
    """
    Calculate source reliability score for a crisis.
    Higher score = more verified by reliable sources.
    """
    session = Session()
    try:
        news = session.query(News).filter(News.crisis_id == crisis_id).all()
        return _reliability_from_news(news)
    finally:
        session.close()


def _reliability_from_news(news_list):
    """Shared scoring logic used by both the single-crisis and batched
    source-reliability helpers, so the two stay consistent."""
    if not news_list:
        return {'reliability': 'unknown', 'score': 50, 'source_count': 0, 'sources': []}

    reliability_scores = []
    unique_sources = set()
    for article in news_list:
        source = article.source or 'Unknown'
        unique_sources.add(source)
        reliability_scores.append(SOURCE_RELIABILITY.get(source, DEFAULT_SOURCE_SCORE))

    avg_score = sum(reliability_scores) / len(reliability_scores)
    source_count = len(unique_sources)

    if source_count >= 3 and avg_score >= 85:
        reliability_level = 'verified'
    elif source_count >= 2 and avg_score >= 75:
        reliability_level = 'corroborated'
    elif source_count >= 1 and avg_score >= 70:
        reliability_level = 'reported'
    else:
        reliability_level = 'unverified'

    return {
        'reliability': reliability_level,
        'score': round(avg_score),
        'source_count': source_count,
        'sources': list(unique_sources)
    }


def calculate_source_reliability_batch(crisis_ids):
    """
    Batched version of calculate_source_reliability() for use when scoring
    many crises at once (e.g. GET /api/crises?include_analysis=true).
    Issues a single query for all News rows instead of one query per crisis.
    Returns { crisis_id: reliability_dict }.
    """
    if not crisis_ids:
        return {}
    session = Session()
    try:
        news = session.query(News).filter(News.crisis_id.in_(crisis_ids)).all()
        by_crisis = defaultdict(list)
        for article in news:
            by_crisis[article.crisis_id].append(article)
        return {cid: _reliability_from_news(by_crisis.get(cid, [])) for cid in crisis_ids}
    finally:
        session.close()
