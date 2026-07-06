"""
Multilingual NewsAPI connector for GeoIntel.
Queries NewsAPI in multiple languages to diversify geographic coverage beyond
the English-language bias of the default connector.

Each language targets specific regions:
  Spanish   → Latin America, Spain
  Arabic    → Middle East, North Africa
  Portuguese→ Brazil, Angola, Mozambique, Portugal
  French    → West Africa, Central Africa, France
  Mandarin  → China, Taiwan (transliterated keywords)
  Russian   → Russia, Central Asia, Eastern Europe
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from data_sources import NewsBasedCrisisDetector

logger = logging.getLogger(__name__)

# Language-specific query configurations
LANGUAGE_CONFIGS = [
    {
        'language': 'es',
        'label': 'Spanish',
        'queries': [
            'conflicto armado',
            'crisis politica',
            'tensiones militares',
            'guerra civil',
            'protestas violencia',
        ],
        'region_hint': 'Latin America / Spain',
    },
    {
        'language': 'ar',
        'label': 'Arabic',
        'queries': [
            'نزاع مسلح',       # armed conflict
            'أزمة سياسية',     # political crisis
            'توترات عسكرية',   # military tensions
            'هجوم إرهابي',     # terrorist attack
        ],
        'region_hint': 'Middle East / North Africa',
    },
    {
        'language': 'pt',
        'label': 'Portuguese',
        'queries': [
            'conflito armado',
            'crise politica',
            'tensoes militares',
            'violencia protestos',
        ],
        'region_hint': 'Brazil / Lusophone Africa',
    },
    {
        'language': 'fr',
        'label': 'French',
        'queries': [
            'conflit armé',
            'crise politique',
            'tensions militaires',
            'violences manifestations',
        ],
        'region_hint': 'Francophone Africa / France',
    },
    {
        'language': 'ru',
        'label': 'Russian',
        'queries': [
            'вооружённый конфликт',   # armed conflict
            'политический кризис',    # political crisis
            'военные учения',         # military exercises
        ],
        'region_hint': 'Russia / Central Asia / Eastern Europe',
    },
]


class MultilingualNewsConnector:
    """Fetch news in multiple languages to expand geographic coverage."""

    def __init__(self):
        self.api_key = os.getenv('NEWS_API_KEY', '')
        self.detector = NewsBasedCrisisDetector()
        self.base_url = 'https://newsapi.org/v2/everything'

    def fetch_articles(self, language_config: dict, days: int = 3) -> list:
        """Fetch articles for one language config."""
        if not self.api_key:
            logger.warning('NEWS_API_KEY not set — skipping multilingual fetch')
            return []

        from_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        articles = []

        for query in language_config['queries']:
            try:
                resp = requests.get(
                    self.base_url,
                    params={
                        'q': query,
                        'language': language_config['language'],
                        'sortBy': 'publishedAt',
                        'pageSize': 30,
                        'from': from_date,
                        'apiKey': self.api_key,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    articles.extend(data.get('articles', []))
                else:
                    logger.warning(
                        f"NewsAPI {language_config['language']}/{query}: HTTP {resp.status_code}"
                    )
            except Exception as e:
                logger.error(f"Multilingual fetch error ({language_config['label']}): {e}")

        return articles

    def detect_crises_from_articles(self, articles: list, language_label: str) -> list:
        """Run crisis detection on fetched articles, returning Crisis-shaped dicts."""
        crises = []
        seen_ids = set()

        for article in articles:
            try:
                # _extract_crisis_from_article takes just the raw article dict — it
                # builds its own title+description text blob internally.
                crisis = self.detector._extract_crisis_from_article(article)
                if crisis and crisis['id'] not in seen_ids:
                    # Tag as multilingual source
                    crisis['source'] = f'NEWS_API_{language_label.upper()}'
                    crises.append(crisis)
                    seen_ids.add(crisis['id'])
            except Exception as e:
                logger.debug(f"Crisis detection skipped: {e}")

        return crises

    def sync_all_languages(self, db_session, days: int = 3) -> int:
        """Fetch news in all configured languages and persist new crises to DB."""
        from models import Crisis

        total_added = 0

        try:
            for lang_config in LANGUAGE_CONFIGS:
                logger.info(
                    f"[Multilingual] Fetching {lang_config['label']} news "
                    f"({lang_config['region_hint']})..."
                )
                articles = self.fetch_articles(lang_config, days=days)
                # Crisis-shaped dicts, not ORM instances — build/merge the model here.
                crisis_dicts = self.detect_crises_from_articles(articles, lang_config['label'])

                for crisis_data in crisis_dicts:
                    existing = db_session.query(Crisis).filter_by(id=crisis_data['id']).first()
                    if not existing:
                        db_session.add(Crisis(**crisis_data))
                        total_added += 1

                if crisis_dicts:
                    logger.info(
                        f"[Multilingual] {lang_config['label']}: "
                        f"{len(articles)} articles → {len(crisis_dicts)} crises"
                    )

            db_session.commit()
            logger.info(f"[Multilingual] Sync complete — {total_added} new crises added")
            return total_added
        except Exception as e:
            db_session.rollback()
            logger.error(f"[Multilingual] Sync failed, rolled back: {e}")
            return total_added
