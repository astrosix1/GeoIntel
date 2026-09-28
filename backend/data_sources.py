"""
Data source connectors for real-world geopolitical data
"""
import requests
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from models import Crisis, CrisisSource, News, Actor, Relationship, EconomicData, CrisisSnapshot, Session
import json
import logging
from dotenv import load_dotenv

import event_pipeline
from event_pipeline.config import get_config
from event_pipeline.keywords import has_keyword, find_keywords, strip_excluded_phrases
from event_pipeline.normalize import stable_news_id, canonical_url
from event_pipeline.titles import acled_title, slug_title, first_sentence
from event_pipeline.location import load_gazetteer, resolve_news_location

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# ACLED replaced its old key+email query-param auth with an OAuth token
# flow (see https://acleddata.com/api-documentation/getting-started) —
# ACLED_BASE below is the real read endpoint (the old value here,
# api.acleddata.com/api/terms, was never a valid ACLED endpoint).
ACLED_OAUTH_URL = "https://acleddata.com/oauth/token"
ACLED_BASE = "https://acleddata.com/api/acled/read"
NEWSAPI_BASE = "https://newsapi.org/v2"
WORLDBANK_BASE = "https://api.worldbank.org/v2"

# GDELT's Event Database — real, free, no key/registration required
# (confirmed live: https://www.gdeltproject.org/data.html states "100% free
# and open"). Added as an ACLED alternative after ACLED's own myACLED access
# system turned out to gate real API reads behind a Research-tier/licensed
# account — see GDELTConnector below. lastupdate.txt always points at the
# 3 real files (export/mentions/gkg) for the most recent 15-minute window;
# GDELT_EVENT_URL_TEMPLATE reconstructs the export file URL for any other
# real, valid 15-minute-aligned timestamp GDELT has published.
GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_EVENT_URL_TEMPLATE = "http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip"

# In-memory cache for the ACLED OAuth token, shared across calls within
# this process — access_token is valid 24h, refresh_token 14 days, so
# re-authenticating (a full username/password POST) on every sync would
# be needlessly slow and hits ACLED's rate limits harder than necessary.
_acled_token_cache = {'access_token': None, 'refresh_token': None, 'expires_at': None}

# Mapping ACLED event types to our crisis types
ACLED_TYPE_MAP = {
    'Violence against civilians': 'conflict',
    'Battle': 'conflict',
    'Explosions/Remote violence': 'conflict',
    'Protests': 'civil_unrest',
    'Riots': 'civil_unrest',
    'Strategic developments': 'military',
    'Armed clash': 'conflict',
    'Cyber attack': 'cyber',
    'Infrastructure attack': 'infrastructure',
    'Displacement': 'migration',
}

# A handful of actor ids in init_actors() aren't real ISO/World Bank country
# codes (EU is an aggregate, NK's real ISO/WB code is KP) — this translates
# those before querying WorldBank or matching an Actor to its EconomicData
# row. Every other actor id already is a real WB/ISO alpha-2 code.
ACTOR_WB_COUNTRY_OVERRIDES = {
    'NK': 'KP',
    'EU': 'EUU',
}

# Crisis type classifications
CRISIS_TYPES = {
    'conflict':       'Active Conflict',
    'military':       'Military Buildup',
    'diplomatic':     'Diplomatic Crisis',
    'economic':       'Economic Shock',
    'resource':       'Resource Conflict',
    'alliance':       'Alliance Shift',
    'proxy':          'Proxy Conflict',
    'technology':     'Tech War',
    'cyber':          'Cyber Attack',
    'infrastructure': 'Infrastructure Attack',
    'migration':      'Migration Crisis',
    'trade_war':      'Trade War',
    'bioweapon':      'Bioweapon Alert',
    'orbital':        'Orbital Conflict',
}


class ACLEDConnector:
    """Fetch real conflict events from ACLED"""

    @staticmethod
    def _get_access_token():
        """
        Returns a valid ACLED OAuth bearer token, authenticating or
        refreshing as needed (see https://acleddata.com/api-documentation/
        getting-started). Returns None if ACLED_EMAIL/ACLED_PASSWORD
        aren't configured, so callers can fall back gracefully.
        """
        cache = _acled_token_cache
        now = datetime.utcnow()

        if cache['access_token'] and cache['expires_at'] and now < cache['expires_at']:
            return cache['access_token']

        email = os.getenv('ACLED_EMAIL')
        password = os.getenv('ACLED_PASSWORD')
        if not email or not password:
            logger.warning("ACLED_EMAIL/ACLED_PASSWORD not set")
            return None

        # A refresh_token (14-day validity) is cheaper than a full
        # username/password re-authentication — try it first if we have one.
        if cache.get('refresh_token'):
            try:
                resp = requests.post(ACLED_OAUTH_URL, data={
                    'grant_type': 'refresh_token',
                    'refresh_token': cache['refresh_token'],
                    'client_id': 'acled',
                }, timeout=10)
                resp.raise_for_status()
                token_data = resp.json()
                cache['access_token'] = token_data['access_token']
                cache['refresh_token'] = token_data.get('refresh_token', cache['refresh_token'])
                cache['expires_at'] = now + timedelta(hours=23)  # 24h validity, 1h safety margin
                return cache['access_token']
            except Exception as e:
                logger.warning(f"ACLED token refresh failed, re-authenticating: {e}")

        try:
            resp = requests.post(ACLED_OAUTH_URL, data={
                'username': email,
                'password': password,
                'grant_type': 'password',
                'client_id': 'acled',
                'scope': 'authenticated',
            }, timeout=10)
            resp.raise_for_status()
            token_data = resp.json()
            cache['access_token'] = token_data['access_token']
            cache['refresh_token'] = token_data.get('refresh_token')
            cache['expires_at'] = now + timedelta(hours=23)
            return cache['access_token']
        except Exception as e:
            logger.error(f"ACLED authentication error: {e}")
            return None

    @staticmethod
    def fetch_recent_events(days=30):
        """
        Fetch recent conflict events from ACLED
        https://acleddata.com/api-documentation/getting-started
        Falls back to sample data if ACLED isn't configured or unavailable.
        """
        try:
            token = ACLEDConnector._get_access_token()
            if not token:
                logger.warning("ACLED not configured — using sample crisis data")
                return ACLEDConnector._get_sample_crises()

            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=days)

            params = {
                '_format': 'json',
                'event_date': f'{start_date}|{end_date}',
                'event_date_where': 'BETWEEN',
                'event_type': '|'.join(ACLED_TYPE_MAP.keys()),
                'limit': 500,
            }
            headers = {'Authorization': f'Bearer {token}'}

            response = requests.get(ACLED_BASE, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            crises = []

            if 'data' in data:
                for event in data['data']:
                    crisis = ACLEDConnector._parse_event(event)
                    if crisis:
                        crises.append(crisis)

            logger.info(f"Fetched {len(crises)} events from ACLED")
            return crises

        except Exception as e:
            logger.error(f"ACLED fetch error: {e}")
            logger.warning("Using sample crisis data instead")
            # Return sample data so platform is still usable
            return ACLEDConnector._get_sample_crises()

    @staticmethod
    def _parse_event(event):
        """Convert ACLED event to Crisis object"""
        try:
            crisis_type = ACLED_TYPE_MAP.get(event.get('event_type'), 'conflict')

            # Calculate severity based on fatalities and participants
            fatalities = int(event.get('fatalities', 0))
            severity = min(100, 30 + (fatalities // 2))  # Scale fatalities to severity

            # Parse ACLED's event_date (YYYY-MM-DD) into a datetime; fall back to now
            event_date_raw = event.get('event_date')
            try:
                date_start = datetime.strptime(event_date_raw, '%Y-%m-%d') if event_date_raw else datetime.utcnow()
            except ValueError:
                date_start = datetime.utcnow()

            # ACLED labels the parties involved directly (actor1/actor2/
            # assoc_actor_1/assoc_actor_2, e.g. "Military Forces of Russia
            # (2000-)") — real, structured stakeholder data, matched against
            # the same curated Actor roster used for news-derived crises
            # rather than trusting ACLED's free-text actor names verbatim.
            actor_text = ' '.join(filter(None, [
                event.get('actor1'), event.get('assoc_actor_1'),
                event.get('actor2'), event.get('assoc_actor_2'),
                event.get('notes'),
            ]))
            stakeholders = NewsBasedCrisisDetector._find_stakeholders(actor_text)

            return {
                'id': f"acled_{event.get('data_id')}",
                'type': crisis_type,
                # event_id_cnty is an ID code ("UKR12345"), not a title — the
                # pipeline's titles stage builds "{sub_event_type} in
                # {location}, {admin1}: N killed" from ACLED's own fields.
                'title': None,
                '_meta': {
                    'kind': 'acled',
                    # ACLED geo_precision: 1 = exact place, 2 = near a town, 3 = region.
                    'precision': {'1': 'point', '2': 'city', '3': 'region'}.get(
                        str(event.get('geo_precision') or '').strip(), 'city'),
                    'fallback_titles': [(acled_title(event), False)],
                    'acled': {k: event.get(k) for k in (
                        'event_type', 'sub_event_type', 'fatalities', 'actor1', 'actor2')},
                },
                'country': event.get('country', 'Unknown'),
                'latitude': float(event.get('latitude', 0)),
                'longitude': float(event.get('longitude', 0)),
                'severity': severity,
                'confidence': 85,  # ACLED is well-documented
                'location_confidence': 85,  # ACLED provides precise coordinates
                'date_start': date_start,  # Crisis model field is date_start, not date
                'analysis': event.get('notes', ''),
                'impact': f"{event.get('fatalities', 0)} fatalities, {event.get('event_type')}",
                'source': 'ACLED',
                'source_id': event.get('data_id'),
                'is_verified': True,
                'stakeholders': ','.join(stakeholders),
            }
        except Exception as e:
            logger.error(f"Error parsing ACLED event: {e}")
            return None

    @staticmethod
    def _get_sample_crises():
        """Return sample crisis data when API is unavailable"""
        from datetime import datetime
        now = datetime.utcnow()

        return [
            {
                'id': 'sample_kyiv',
                'type': 'conflict',
                'title': 'Kyiv Conflict Zone',
                'country': 'Kyiv',
                'latitude': 50.4501,
                'longitude': 30.5234,
                'severity': 95,
                'confidence': 92,
                'location_confidence': 88,
                'date_start': now,
                'analysis': 'Ongoing military conflict in Kyiv region with NATO support.',
                'impact': 'Massive humanitarian crisis, European energy disruption.',
                'source': 'Sample Data',
                'source_id': 'sample_001',
                'is_verified': True,
            },
            {
                'id': 'sample_beijing',
                'type': 'conflict',
                'title': 'China-Taiwan Military Tensions',
                'country': 'Beijing',
                'latitude': 39.9042,
                'longitude': 116.4074,
                'severity': 85,
                'confidence': 76,
                'location_confidence': 85,
                'date_start': now,
                'analysis': 'Escalating military tensions in the Taiwan Strait region.',
                'impact': 'Global semiconductor supply disruption.',
                'source': 'Sample Data',
                'source_id': 'sample_002',
                'is_verified': True,
            },
            {
                'id': 'sample_tehran',
                'type': 'proxy',
                'title': 'Tehran Regional Tensions',
                'country': 'Tehran',
                'latitude': 35.6892,
                'longitude': 51.3890,
                'severity': 74,
                'confidence': 88,
                'location_confidence': 90,
                'date_start': now,
                'analysis': 'Multi-theater proxy conflicts involving Iranian forces.',
                'impact': 'Regional destabilization, oil market volatility.',
                'source': 'Sample Data',
                'source_id': 'sample_003',
                'is_verified': True,
            },
            {
                'id': 'sample_gaza',
                'type': 'conflict',
                'title': 'Gaza Humanitarian Crisis',
                'country': 'Gaza',
                'latitude': 31.5,
                'longitude': 34.5,
                'severity': 80,
                'confidence': 95,
                'location_confidence': 92,
                'date_start': now,
                'analysis': 'Ongoing Gaza conflict with massive humanitarian consequences.',
                'impact': 'Humanitarian catastrophe, international crisis.',
                'source': 'Sample Data',
                'source_id': 'sample_004',
                'is_verified': True,
            },
            {
                'id': 'sample_moscow',
                'type': 'technology',
                'title': 'Moscow Cyber Operations',
                'country': 'Moscow',
                'latitude': 55.7558,
                'longitude': 37.6173,
                'severity': 70,
                'confidence': 92,
                'location_confidence': 89,
                'date_start': now,
                'analysis': 'Ongoing cyber and information warfare operations.',
                'impact': 'Global infrastructure risks, geopolitical tension.',
                'source': 'Sample Data',
                'source_id': 'sample_005',
                'is_verified': True,
            },
            # ── SOUTHERN HEMISPHERE CRISES ──
            {
                'id': 'sample_caracas',
                'type': 'migration',
                'title': 'Venezuelan Humanitarian Crisis',
                'country': 'Venezuela',
                'latitude': 10.4806,
                'longitude': -66.9036,
                'severity': 82,
                'confidence': 89,
                'location_confidence': 85,
                'date_start': now - timedelta(days=8),
                'analysis': 'Ongoing economic collapse and political repression causing massive refugee flows to neighboring countries. Supply shortages and infrastructure collapse.',
                'impact': 'Regional destabilization, humanitarian emergency affecting 7+ million people, strain on neighboring economies.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_001',
                'is_verified': True,
            },
            {
                'id': 'sample_yangon',
                'type': 'conflict',
                'title': 'Myanmar Military Conflict',
                'country': 'Myanmar',
                'latitude': 16.8661,
                'longitude': 96.1951,
                'severity': 78,
                'confidence': 91,
                'location_confidence': 87,
                'date_start': now - timedelta(days=12),
                'analysis': 'Military junta conflict with resistance forces. Ethnic minorities facing persecution. Regional spillover into Thailand and Bangladesh.',
                'impact': 'Rohingya refugee crisis, humanitarian catastrophe, regional instability affecting ASEAN.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_002',
                'is_verified': True,
            },
            {
                'id': 'sample_kinshasa',
                'type': 'resource',
                'title': 'Eastern DRC Resource Conflict',
                'country': 'Democratic Republic of Congo',
                'latitude': -4.3369,
                'longitude': 15.3136,
                'severity': 76,
                'confidence': 85,
                'location_confidence': 80,
                'date_start': now - timedelta(days=5),
                'analysis': 'Competition over rare earth minerals and cobalt deposits fueling armed militia conflicts. Chinese corporate interests competing with Western mining operations.',
                'impact': 'Global semiconductor supply threats, humanitarian crisis, regional destabilization.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_003',
                'is_verified': True,
            },
            {
                'id': 'sample_pretoria',
                'type': 'economic',
                'title': 'South Africa Water & Power Crisis',
                'country': 'South Africa',
                'latitude': -25.7479,
                'longitude': 28.2293,
                'severity': 71,
                'confidence': 87,
                'location_confidence': 88,
                'date_start': now - timedelta(days=15),
                'analysis': 'Critical water shortages in major cities combined with electricity grid collapse. Infrastructure failure threatening economic activity.',
                'impact': 'Economic contraction, civil unrest, food security threats affecting 60 million people.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_004',
                'is_verified': True,
            },
            {
                'id': 'sample_buenos_aires',
                'type': 'economic',
                'title': 'Argentina Economic Instability',
                'country': 'Argentina',
                'latitude': -34.6037,
                'longitude': -58.3816,
                'severity': 68,
                'confidence': 92,
                'location_confidence': 90,
                'date_start': now - timedelta(days=18),
                'analysis': 'Currency collapse and inflation spiraling, debt restructuring negotiations, political polarization.',
                'impact': 'Regional economic contagion risk, poverty surge, social unrest.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_005',
                'is_verified': True,
            },
            {
                'id': 'sample_jakarta',
                'type': 'technology',
                'title': 'Indonesia Cyber & Maritime Tensions',
                'country': 'Indonesia',
                'latitude': -6.2088,
                'longitude': 106.8456,
                'severity': 65,
                'confidence': 82,
                'location_confidence': 83,
                'date_start': now - timedelta(days=20),
                'analysis': 'Chinese cyber operations targeting Indonesian infrastructure. South China Sea maritime disputes affecting shipping routes.',
                'impact': 'Regional supply chain disruption, geopolitical tension in Southeast Asia.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_006',
                'is_verified': True,
            },
            {
                'id': 'sample_sao_paulo',
                'type': 'resource',
                'title': 'Amazon Deforestation & Climate Crisis',
                'country': 'Brazil',
                'latitude': -23.5505,
                'longitude': -46.6333,
                'severity': 72,
                'confidence': 88,
                'location_confidence': 86,
                'date_start': now - timedelta(days=10),
                'analysis': 'Accelerated deforestation driven by cattle ranching and illegal mining. Indigenous territories under threat. Tipping point risk for Amazon rainforest.',
                'impact': 'Global climate implications, indigenous displacement, biodiversity collapse.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_007',
                'is_verified': True,
            },
            {
                'id': 'sample_la_paz',
                'type': 'diplomatic',
                'title': 'Bolivia Political Crisis',
                'country': 'Bolivia',
                'latitude': -16.5,
                'longitude': -68.15,
                'severity': 62,
                'confidence': 79,
                'location_confidence': 80,
                'date_start': now - timedelta(days=3),
                'analysis': 'Political instability following disputed elections. Indigenous-led movements challenging resource extraction policies.',
                'impact': 'Regional instability, lithium supply uncertainty affecting EV markets.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_008',
                'is_verified': True,
            },
            {
                'id': 'sample_canberra',
                'type': 'military',
                'title': 'Australia Regional Security Buildup',
                'country': 'Australia',
                'latitude': -35.2809,
                'longitude': 149.1300,
                'severity': 58,
                'confidence': 85,
                'location_confidence': 87,
                'date_start': now - timedelta(days=22),
                'analysis': 'Australian military expansion and AUKUS alliance strengthening in response to Chinese assertiveness in Indo-Pacific.',
                'impact': 'Regional arms race, strategic competition for dominance of sea lanes.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_009',
                'is_verified': True,
            },
            {
                'id': 'sample_lima',
                'type': 'resource',
                'title': 'Peru Drug Trafficking & Political Instability',
                'country': 'Peru',
                'latitude': -12.0464,
                'longitude': -77.0428,
                'severity': 64,
                'confidence': 83,
                'location_confidence': 84,
                'date_start': now - timedelta(days=14),
                'analysis': 'Powerful drug cartels competing for cocaine production and trafficking routes. Political leadership challenged by organized crime.',
                'impact': 'Regional narcotics flows, violence, governance instability.',
                'source': 'Sample Data',
                'source_id': 'sample_sh_010',
                'is_verified': True,
            },
        ]


class NewsAPIConnector:
    """Fetch contextual news from NewsAPI"""

    @staticmethod
    def fetch_geopolitical_news(q="geopolitical conflict", days=7):
        """
        Fetch news articles related to geopolitical crises
        Requires NEWSAPI_KEY from .env
        """
        try:
            api_key = os.getenv('NEWSAPI_KEY')
            if not api_key:
                logger.warning("NEWSAPI_KEY not set")
                return []

            from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            params = {
                'q': q,
                'sortBy': 'publishedAt',
                'language': 'en',
                'apiKey': api_key,
                'pageSize': 100,
            }

            response = requests.get(
                f"{NEWSAPI_BASE}/everything",
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            articles = []

            for article in data.get('articles', []):
                news_item = NewsAPIConnector._parse_article(article)
                if news_item:
                    articles.append(news_item)

            logger.info(f"Fetched {len(articles)} articles from NewsAPI")
            return articles

        except Exception as e:
            logger.error(f"NewsAPI fetch error: {e}")
            return []

    @staticmethod
    def _parse_article(article):
        """Convert NewsAPI article to News object"""
        try:
            from textblob import TextBlob

            # Simple sentiment analysis
            blob = TextBlob(article.get('title', '') + ' ' + article.get('description', ''))
            sentiment_score = blob.sentiment.polarity  # -1 to 1
            sentiment = 'positive' if sentiment_score > 0.1 else 'negative' if sentiment_score < -0.1 else 'neutral'

            # News.published_at is a DateTime column — NewsAPI returns an
            # ISO 8601 string (e.g. "2026-09-20T10:00:00Z"), which SQLite
            # rejects outright if passed through unparsed. That used to
            # break every single news upsert, which cascaded into failing
            # the whole sync's session.commit() (SQLAlchemy leaves a
            # session unusable after a flush error) — silently discarding
            # everything else the sync had queued, crises included.
            published_at_raw = article.get('publishedAt')
            try:
                published_at = (
                    datetime.fromisoformat(published_at_raw.replace('Z', '+00:00'))
                    if published_at_raw else datetime.utcnow()
                )
            except (ValueError, AttributeError):
                published_at = datetime.utcnow()

            return {
                'id': article.get('url', '').replace('/', '_'),
                'title': article.get('title'),
                'url': article.get('url'),
                'source': article.get('source', {}).get('name', 'Unknown'),
                'content': article.get('description', ''),
                'published_at': published_at,
                'sentiment': sentiment,
                'sentiment_score': sentiment_score,
            }
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None


class NewsBasedCrisisDetector:
    """Extract real crises from news articles"""

    # Curated city table for placing news articles — lives in
    # config/gazetteer.json (lower-case name -> lat/lon/country). Location
    # resolution itself (scoring, metonymy, ambiguous names) is in
    # event_pipeline/location.py.
    LOCATION_MAP = load_gazetteer()

    # Keywords for crisis type detection live in config/event_filters.json
    # ("news_crisis_keywords"). Dict order matters — first match wins (see
    # _extract_crisis_from_article) — so leadership_change and civil_unrest
    # come before conflict/military, since a coup or protest story often
    # also contains generic "armed"/"military" words. Matching is always
    # word-boundary (event_pipeline.keywords), never a raw substring check.
    CRISIS_KEYWORDS = get_config()['news_crisis_keywords']

    # Wire-service articles conventionally open with a dateline naming the
    # REPORTING BUREAU's city, not necessarily the story's subject — e.g.
    # "LIMA, Sept 20 (Reuters) - Officials warned that conflict is
    # worsening across the Sahel..." is a story about Africa, datelined
    # from Lima. Matching that blindly mis-geocoded several real articles
    # to the dateline city instead of the story's actual location, so it's
    # stripped from the description before city-matching runs.
    DATELINE_RE = re.compile(r'^\s*[A-Z][A-Za-z0-9.,\s]{1,40}\([^)]{1,30}\)\s*[-–—]\s*')

    # Lazily-built, cached (pattern, actor_id) list from the real Actor
    # roster — rebuilt once per process, same reasoning as
    # the city patterns in event_pipeline/location.py. The roster is curated seed data (init_actors)
    # that doesn't change while a process is running.
    _actor_name_patterns = None
    _actor_roster_warned = False

    @staticmethod
    def _get_actor_name_patterns():
        if NewsBasedCrisisDetector._actor_name_patterns is None:
            session = Session()
            try:
                actors = session.query(Actor).all()
                NewsBasedCrisisDetector._actor_name_patterns = [
                    (re.compile(r'\b' + re.escape(a.name) + r'\b', re.IGNORECASE), a.id)
                    for a in actors
                ]
            except Exception as e:
                # No actors table yet (e.g. scripts/preview_pipeline.py against
                # a fresh database) — stakeholder matching just finds nothing,
                # rather than failing every connector's parse. Not cached, so
                # it retries once the table exists.
                if not NewsBasedCrisisDetector._actor_roster_warned:
                    NewsBasedCrisisDetector._actor_roster_warned = True
                    logger.warning(f"Actor roster unavailable for stakeholder matching "
                                   f"({type(e).__name__}); stakeholders will be empty")
                return []
            finally:
                session.close()
        return NewsBasedCrisisDetector._actor_name_patterns

    @staticmethod
    def _find_stakeholders(text):
        """
        Real actor ids whose full name (from the curated Actor roster)
        appears in `text`, word-boundary matched.
        Returns [] when nothing matches confidently — Crisis.stakeholders
        had zero writers before this, so any populated value here must be
        a real, traceable match, never a guessed/default actor list.
        """
        return [
            actor_id
            for pattern, actor_id in NewsBasedCrisisDetector._get_actor_name_patterns()
            if pattern.search(text)
        ]

    @staticmethod
    def extract_crises_from_news(days=7):
        """Extract real crises from news articles"""
        try:
            api_key = os.getenv('NEWSAPI_KEY')
            if not api_key:
                logger.warning("NEWSAPI_KEY not set")
                return []

            # Fetch geopolitical news
            from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            search_queries = [
                'military conflict war',
                'geopolitical crisis',
                'international tension',
                'military buildup',
                'diplomatic crisis',
                'armed clash',
            ]

            crises = []
            seen_titles = set()

            for query in search_queries:
                try:
                    params = {
                        'q': query,
                        'sortBy': 'publishedAt',
                        'language': 'en',
                        'apiKey': api_key,
                        'pageSize': 20,
                    }

                    response = requests.get(
                        f"{NEWSAPI_BASE}/everything",
                        params=params,
                        timeout=10
                    )
                    response.raise_for_status()

                    data = response.json()

                    for article in data.get('articles', []):
                        # Skip duplicates
                        title = article.get('title', '')
                        if title in seen_titles:
                            continue
                        seen_titles.add(title)

                        crisis = NewsBasedCrisisDetector._extract_crisis_from_article(article)
                        if crisis:
                            crises.append(crisis)

                except Exception as e:
                    logger.warning(f"Error fetching news query '{query}': {e}")
                    continue

            logger.info(f"Extracted {len(crises)} crises from news articles")
            return crises

        except Exception as e:
            logger.error(f"News-based crisis detection error: {e}")
            return []

    @staticmethod
    def _extract_crisis_from_article(article):
        """Extract crisis data from a news article"""
        try:
            title = article.get('title', '') or ''
            description = article.get('description', '') or ''
            source = article.get('source', {}).get('name', 'News')
            published = article.get('publishedAt', '')
            url = article.get('url', '')

            # Strip a leading wire-service dateline (see DATELINE_RE) before
            # combining title+description for location matching, so a
            # bureau city unrelated to the story can't win by default.
            description_for_location = NewsBasedCrisisDetector.DATELINE_RE.sub('', description, count=1)
            text_lower = (title + ' ' + description_for_location).lower()

            # Topic-relevance check runs FIRST, before any geocoding. REQUIRE
            # at least one crisis-relevant keyword to actually be present —
            # this used to default to 'conflict' when nothing matched, which
            # meant the only real gate on "is this a crisis" was having a
            # recognized city name. Matching is word-boundary only, after
            # stripping idioms like "heart attack" / "price war": the old
            # substring test let 'ai' match "said" and 'war' match
            # "software"/"Warsaw", so almost any article passed.
            match_text = strip_excluded_phrases(text_lower)
            crisis_type = None
            for ctype, keywords in NewsBasedCrisisDetector.CRISIS_KEYWORDS.items():
                if has_keyword(match_text, keywords):
                    crisis_type = ctype
                    break

            if crisis_type is None:
                return None

            # Placement scores every city/country mention (title over
            # description, "in/near X" over a passing mention) instead of
            # taking the first city, and skips capitals used to mean their
            # government ("Washington warns Tehran" -> Iran, at country
            # precision) and ambiguous names like "Victoria" unless their
            # country is also named. The dateline was stripped above. See
            # event_pipeline/location.py.
            place = resolve_news_location(title, description_for_location)
            if not place:
                return None
            lat, lon, country = place['lat'], place['lon'], place['country']
            location_confidence = 82 if place['precision'] == 'city' else 55

            # Interim keyword severity (highest matching weight wins, word-
            # boundary matched) until event_pipeline scoring replaces it.
            severity_cfg = get_config()['news_severity_keywords']
            weights = severity_cfg['weights']
            severity = severity_cfg['base']
            for keyword in find_keywords(match_text, list(weights)):
                severity = max(severity, weights[keyword])

            # Stable, per-article id from the canonical URL. The old
            # f"news_{source}_{date}" id collided for every article one
            # outlet published that day, so they overwrote each other.
            crisis_id = stable_news_id(url or f"{source}|{title}|{published}")

            # Real actor ids mentioned by name in the article — [] when
            # nothing matches, never a guessed default (see _find_stakeholders).
            stakeholders = NewsBasedCrisisDetector._find_stakeholders(title + ' ' + description)

            return {
                'id': crisis_id,
                'type': crisis_type,
                'title': title,  # cleaned (outlet/date/tags stripped) by the pipeline's titles stage
                '_meta': {
                    'kind': 'news',
                    'precision': place['precision'],
                    'parties': place['parties'],
                    'outlet': source,
                    'url': url,
                    'text': title + ' ' + description_for_location,
                    'fallback_titles': [(first_sentence(description_for_location), True)],
                },
                'country': country,   # actual country (e.g. "Iran")
                'latitude': lat,      # exact city lat
                'longitude': lon,     # exact city lon
                'severity': min(100, severity),
                'confidence': 75,
                'location_confidence': location_confidence,  # curated city match
                'date_start': datetime.fromisoformat(published.replace('Z', '+00:00')) if published else datetime.utcnow(),
                'analysis': description[:500] if description else title,
                'impact': f"Reported by {source}",
                'source': 'NewsAPI',
                'source_id': canonical_url(url) or url,  # clamped to the column width by the pipeline
                'is_verified': False,
                'stakeholders': ','.join(stakeholders),
            }

        except Exception as e:
            logger.error(f"Error extracting crisis from article: {e}")
            return None


class WorldBankConnector:
    """Fetch economic data from World Bank"""

    # Map World Bank indicator codes to the matching EconomicData model column
    INDICATOR_FIELD_MAP = {
        'NY.GDP.MKTP.CD': 'gdp',            # GDP (current US$) — converted to billions below
        'NY.GDP.MKTP.KD.ZG': 'gdp_growth',  # GDP growth (annual %)
        'NE.EXP.GNFS.CD': 'exports',        # Exports of goods and services (current US$, billions)
        'NE.IMP.GNFS.CD': 'imports',        # Imports of goods and services (current US$, billions)
        'FP.CPI.TOTL.ZG': 'inflation',      # Inflation (annual %)
        'SL.UEM.TOTL.ZS': 'unemployment',   # Unemployment rate (%)
    }

    @staticmethod
    def derive_country_codes(session):
        """Real WorldBank/ISO country codes for every actor currently
        tracked (translating the handful of non-ISO actor ids — EU, NK —
        via ACTOR_WB_COUNTRY_OVERRIDES). Replaces the old hardcoded
        6-country default: coverage now grows automatically with the actor
        roster instead of needing a separately maintained list. Falls back
        to the original 6-country default if the actor table is empty
        (e.g. called before init_actors() has ever run)."""
        actors = session.query(Actor).all()
        if not actors:
            return ['US', 'CN', 'RU', 'JP', 'DE', 'IN']
        codes = {ACTOR_WB_COUNTRY_OVERRIDES.get(a.id, a.id) for a in actors}
        return sorted(codes)

    @staticmethod
    def fetch_country_indicators(country_codes=['US', 'CN', 'RU', 'JP', 'DE', 'IN']):
        """
        Fetch economic indicators for countries and merge them into one
        EconomicData-shaped record per (country, year), matching the model's columns.
        """
        try:
            # per_country[country][year] = {field_name: value, ...}
            per_country = defaultdict(lambda: defaultdict(dict))

            for country in country_codes:
                for ind_code, field_name in WorldBankConnector.INDICATOR_FIELD_MAP.items():
                    try:
                        response = requests.get(
                            f"{WORLDBANK_BASE}/country/{country}/indicator/{ind_code}",
                            params={'format': 'json', 'per_page': 10},
                            timeout=10
                        )
                        response.raise_for_status()

                        data = response.json()
                        if len(data) > 1 and data[1]:
                            for record in data[1]:
                                value = record.get('value')
                                year_raw = record.get('date')
                                if value is None or not year_raw:
                                    continue
                                year = int(year_raw)
                                # GDP/exports/imports come back in raw USD — convert to billions
                                if field_name in ('gdp', 'exports', 'imports'):
                                    value = value / 1e9
                                per_country[country][year][field_name] = value

                    except Exception as e:
                        logger.warning(f"Error fetching {ind_code} for {country}: {e}")

            # Flatten into one dict per (country, year) matching EconomicData columns
            economic_data = []
            for country, years in per_country.items():
                for year, fields in years.items():
                    if not fields:
                        continue
                    economic_data.append({
                        'id': f"wb_{country}_{year}",
                        'country_code': country,
                        'year': year,
                        **fields,
                    })

            logger.info(f"Fetched {len(economic_data)} economic records")
            return economic_data

        except Exception as e:
            logger.error(f"World Bank fetch error: {e}")
            return []


# CAMEO event root codes (2-digit prefix of EventCode) mapped to this app's
# crisis types, mirroring ACLED_TYPE_MAP's pattern above. Only the codes
# that can actually appear under GDELTConnector's QuadClass 3/4 filter
# (verbal + material conflict) are listed — codes 01-09 (cooperation) never
# reach this map since those rows are filtered out before type lookup.
GDELT_TYPE_MAP = {
    '10': 'diplomatic',    # DEMAND
    '11': 'diplomatic',    # DISAPPROVE
    '12': 'diplomatic',    # REJECT
    '13': 'diplomatic',    # THREATEN
    '14': 'civil_unrest',  # PROTEST
    '15': 'military',      # EXHIBIT FORCE POSTURE
    '16': 'diplomatic',    # REDUCE RELATIONS
    '17': 'diplomatic',    # COERCE
    '18': 'conflict',      # ASSAULT
    '19': 'conflict',      # FIGHT
    '20': 'conflict',      # USE UNCONVENTIONAL MASS VIOLENCE
}


class GDELTConnector:
    """
    Free, real alternative/addition to ACLED — the GDELT Project's Event
    Database (https://www.gdeltproject.org/data.html, confirmed live as
    "100% free and open", no registration or key). Monitors global news
    every 15 minutes and publishes structured, CAMEO-coded events with real
    lat/lon, the same shape of data ACLED provides.

    File format: tab-separated, no header, 61 fixed columns per row. Column
    positions below were verified by downloading and inspecting a real live
    file during development, not just the public docs, since off-by-one
    errors in this schema are a known pitfall.
    """
    _COL_ACTOR1_CODE = 5
    _COL_ACTOR1_COUNTRY = 7
    _COL_ACTOR1_TYPE = 12
    _COL_ACTOR2_CODE = 15
    _COL_ACTOR2_COUNTRY = 17
    _COL_ACTOR2_TYPE = 22
    _COL_IS_ROOT_EVENT = 25
    _COL_EVENT_CODE = 26
    _COL_EVENT_BASE_CODE = 27
    _COL_EVENT_ROOT_CODE = 28
    _COL_QUAD_CLASS = 29
    _COL_GOLDSTEIN = 30
    _COL_NUM_SOURCES = 32
    _COL_NUM_ARTICLES = 33
    _COL_ACTOR1_NAME = 6
    _COL_ACTOR2_NAME = 16
    _COL_ACTION_GEO_TYPE = 51
    _COL_ACTION_GEO_FULLNAME = 52
    _COL_ACTION_GEO_LAT = 56
    _COL_ACTION_GEO_LONG = 57
    _COL_DATE_ADDED = 59
    _COL_SOURCE_URL = 60
    _MIN_COLUMNS = 61

    @staticmethod
    def _get_recent_timestamps():
        """The real, currently-published GDELT event-file timestamp (from
        lastupdate.txt) plus the 3 that precede it at 15-minute intervals —
        covers a full hour so nothing is missed between this app's hourly
        sync runs. No persisted sync-cursor needed: `_upsert_crisis()`
        already dedups by id, so a little overlap between runs is harmless,
        the same way ACLED/NewsAPI's own rolling-window fetches work."""
        response = requests.get(GDELT_LASTUPDATE_URL, timeout=10)
        response.raise_for_status()

        latest_ts = None
        for line in response.text.splitlines():
            if '.export.CSV.zip' in line:
                url = line.strip().split()[-1]
                latest_ts = url.rsplit('/', 1)[-1].split('.export.CSV.zip')[0]
                break
        if not latest_ts:
            raise ValueError("lastupdate.txt did not contain an export.CSV.zip entry")

        latest_dt = datetime.strptime(latest_ts, '%Y%m%d%H%M%S')
        return [(latest_dt - timedelta(minutes=15 * i)).strftime('%Y%m%d%H%M%S') for i in range(4)]

    @staticmethod
    def _fetch_event_rows(timestamp):
        """Download and unzip one real GDELT event file, returning its raw
        tab-separated rows. Returns [] on any failure (network, missing
        file — GDELT occasionally publishes late) rather than raising, so
        one bad window never breaks the other 3."""
        import zipfile
        import io

        url = GDELT_EVENT_URL_TEMPLATE.format(ts=timestamp)
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                name = zf.namelist()[0]
                text = zf.read(name).decode('utf-8', errors='replace')
            return [line.split('\t') for line in text.splitlines() if line.strip()]
        except Exception as e:
            logger.warning(f"GDELT fetch failed for {timestamp}: {e}")
            return []

    @staticmethod
    def _country_from_geo_fullname(full_name):
        """GDELT's ActionGeo_CountryCode is FIPS 10-4, not ISO — this app's
        Crisis.country convention is a real country NAME string (matching
        Actor.name, per LOCATION_MAP/ACLED's own convention). ActionGeo_
        FullName is a real, already-geocoded hierarchical description
        ("City, Admin1, Country" or just "Country" for a country-level
        geo-type) — the country name is reliably its last comma segment,
        confirmed against real sample rows during development, so this
        parses it directly rather than maintaining a ~200-entry FIPS
        lookup table."""
        if not full_name:
            return None
        parts = [p.strip() for p in full_name.split(',') if p.strip()]
        return parts[-1] if parts else None

    @staticmethod
    def _parse_row(fields):
        """One raw TSV row -> a crisis dict, or None if it's not a real
        conflict-relevant row (wrong QuadClass, unmapped event type, or
        missing the geo/severity data a real crisis record needs)."""
        if len(fields) < GDELTConnector._MIN_COLUMNS:
            return None

        quad_class = fields[GDELTConnector._COL_QUAD_CLASS]
        if quad_class not in ('3', '4'):  # keep only verbal + material conflict
            return None

        event_root = fields[GDELTConnector._COL_EVENT_CODE][:2]
        crisis_type = GDELT_TYPE_MAP.get(event_root)
        if crisis_type is None:
            return None

        try:
            lat = float(fields[GDELTConnector._COL_ACTION_GEO_LAT])
            lon = float(fields[GDELTConnector._COL_ACTION_GEO_LONG])
        except (ValueError, IndexError):
            return None
        if lat == 0 and lon == 0:  # GDELT's placeholder for "no real geo resolved"
            return None

        country = GDELTConnector._country_from_geo_fullname(
            fields[GDELTConnector._COL_ACTION_GEO_FULLNAME]
        )
        if not country:
            return None

        # Severity — real, not fabricated: GoldsteinScale is GDELT's own
        # published -10 (maximally conflictual) .. +10 (maximally
        # cooperative) intensity score for this exact event. A maximally
        # conflictual event scores 100; anything trending cooperative
        # (rare but possible even inside QuadClass 3/4's edge cases)
        # clamps to a low, not negative, severity.
        try:
            goldstein = float(fields[GDELTConnector._COL_GOLDSTEIN])
        except (ValueError, IndexError):
            goldstein = 0.0
        severity = max(0, min(100, round(-goldstein * 10)))

        # Confidence — real, not a flat constant: more independent sources
        # corroborating the same event is a real (if rough) signal.
        try:
            num_sources = int(float(fields[GDELTConnector._COL_NUM_SOURCES]))
        except (ValueError, IndexError):
            num_sources = 1
        confidence = max(50, min(95, 50 + num_sources * 5))

        global_event_id = fields[0]
        date_added_raw = fields[GDELTConnector._COL_DATE_ADDED]
        try:
            date_start = datetime.strptime(date_added_raw, '%Y%m%d%H%M%S')
        except ValueError:
            date_start = datetime.utcnow()

        actor_text = fields[GDELTConnector._COL_ACTOR1_NAME] + ' ' + fields[GDELTConnector._COL_ACTOR2_NAME]
        stakeholders = NewsBasedCrisisDetector._find_stakeholders(actor_text)

        source_url = fields[GDELTConnector._COL_SOURCE_URL]
        headline = slug_title(source_url)
        try:
            num_articles = int(float(fields[GDELTConnector._COL_NUM_ARTICLES]))
        except (ValueError, IndexError):
            num_articles = 0

        return {
            'id': f"gdelt_{global_event_id}",
            'type': crisis_type,
            # GDELT has no headline. The titles stage tries the article URL's
            # slug first (usually the real headline), then a CAMEO phrase
            # built from the actors, event code and place.
            'title': None,
            '_meta': {
                'kind': 'gdelt',
                'url': source_url,
                'headline': headline,
                'gdelt': {
                    'is_root_event': fields[GDELTConnector._COL_IS_ROOT_EVENT],
                    'event_code': fields[GDELTConnector._COL_EVENT_CODE],
                    'base_code': fields[GDELTConnector._COL_EVENT_BASE_CODE],
                    'num_sources': num_sources,
                    'num_articles': num_articles,
                    'actor1_name': fields[GDELTConnector._COL_ACTOR1_NAME],
                    'actor2_name': fields[GDELTConnector._COL_ACTOR2_NAME],
                    'actor1_code': fields[GDELTConnector._COL_ACTOR1_CODE],
                    'actor1_country': fields[GDELTConnector._COL_ACTOR1_COUNTRY],
                    'actor1_type': fields[GDELTConnector._COL_ACTOR1_TYPE],
                    'actor2_code': fields[GDELTConnector._COL_ACTOR2_CODE],
                    'actor2_country': fields[GDELTConnector._COL_ACTOR2_COUNTRY],
                    'actor2_type': fields[GDELTConnector._COL_ACTOR2_TYPE],
                },
                'fallback_titles': [(headline, True)],
                # CAMEO-phrased fallback title, built by the titles stage
                # once the location stage has settled on the place.
                'cameo': {
                    'actor1': fields[GDELTConnector._COL_ACTOR1_NAME],
                    'actor2': fields[GDELTConnector._COL_ACTOR2_NAME],
                    'event_code': fields[GDELTConnector._COL_EVENT_CODE],
                    'base_code': fields[GDELTConnector._COL_EVENT_BASE_CODE],
                    'root_code': fields[GDELTConnector._COL_EVENT_ROOT_CODE],
                },
                'place_full_name': fields[GDELTConnector._COL_ACTION_GEO_FULLNAME],
                'precision': {'1': 'country', '2': 'region', '5': 'region', '3': 'city', '4': 'city'}.get(
                    fields[GDELTConnector._COL_ACTION_GEO_TYPE], 'city'),
                # Each actor's own geo — used when ActionGeo lands in a
                # country that isn't party to the event.
                'alt_geos': [
                    {'type': fields[t], 'full_name': fields[n], 'lat': fields[la], 'lon': fields[lo]}
                    for t, n, la, lo in ((35, 36, 40, 41), (43, 44, 48, 49))
                    if fields[n]
                ],
            },
            'country': country,
            'latitude': lat,
            'longitude': lon,
            'severity': severity,
            'confidence': confidence,
            'location_confidence': 85,  # GDELT's own geocoding, not text inference
            'date_start': date_start,
            'analysis': f"GDELT-monitored event (CAMEO {fields[GDELTConnector._COL_EVENT_CODE]}), reported via {source_url}",
            'impact': f"{num_sources} source(s) reporting",
            'source': 'GDELT',
            'source_id': global_event_id,
            'is_verified': False,
            'stakeholders': ','.join(stakeholders),
        }

    @staticmethod
    def fetch_recent_events():
        """Real, current conflict-relevant events from GDELT — covers the
        last hour (4 real 15-minute files) so nothing is missed between
        this app's hourly sync runs. Returns [] (never raises) on total
        failure, matching ACLED/NewsAPI's own graceful-degradation pattern."""
        try:
            timestamps = GDELTConnector._get_recent_timestamps()
        except Exception as e:
            logger.error(f"GDELT lastupdate.txt fetch failed: {e}")
            return []

        crises = []
        seen_ids = set()
        for ts in timestamps:
            for fields in GDELTConnector._fetch_event_rows(ts):
                crisis = GDELTConnector._parse_row(fields)
                if crisis and crisis['id'] not in seen_ids:
                    seen_ids.add(crisis['id'])
                    crises.append(crisis)

        logger.info(f"Fetched {len(crises)} conflict-relevant events from GDELT")
        return crises


class DataAggregator:
    """Aggregate data from multiple sources into Crisis records"""

    @staticmethod
    def sync_all_sources():
        """Fetch and sync all data sources"""
        logger.info("Starting data sync...")

        session = Session()
        report = event_pipeline.PipelineReport(label='sync')

        try:
            # Every connector's candidates go through the event pipeline
            # (event_pipeline.process_batch) before being written — that's
            # where validation, filtering and dedup live, with a reason code
            # for every rejection (see docs/EVENT_FILTERING.md).

            # Try ACLED first (if available)
            acled_crises = ACLEDConnector.fetch_recent_events(days=30)
            DataAggregator._upsert_batch(session, acled_crises, 'ACLED', report)

            # GDELT — free, real, no-key alternative/addition to ACLED
            # (see GDELTConnector). Caught locally rather than letting a
            # GDELT-side failure bubble to this function's outer except,
            # which would roll back the ACLED/news/economic work already
            # staged in this same session — a GDELT hiccup must only cost
            # GDELT's own rows, never the rest of the sync.
            try:
                gdelt_crises = GDELTConnector.fetch_recent_events()
                DataAggregator._upsert_batch(session, gdelt_crises, 'GDELT', report)
            except Exception as e:
                logger.error(f"GDELT sync error: {e}")

            # Also fetch real crises from news articles
            news_crises = NewsBasedCrisisDetector.extract_crises_from_news(days=7)
            DataAggregator._upsert_batch(session, news_crises, 'NewsAPI', report)

            # Fetch News articles for context
            news_articles = NewsAPIConnector.fetch_geopolitical_news()
            for article_data in news_articles:
                DataAggregator._upsert_news(session, article_data)

            # Fetch Economic Data — country list now derives from the real
            # actor roster (see WorldBankConnector.derive_country_codes)
            # instead of a hardcoded 6-country default.
            country_codes = WorldBankConnector.derive_country_codes(session)
            econ_data = WorldBankConnector.fetch_country_indicators(country_codes)
            for econ_item in econ_data:
                DataAggregator._upsert_economic(session, econ_item)

            DataAggregator.expire_stale(session)

            session.commit()
            logger.info("Data sync completed successfully")
            logger.info(report.summary_line())
            event_pipeline.remember(report)

        except Exception as e:
            session.rollback()
            logger.error(f"Data sync error: {e}")
        finally:
            session.close()

        # Separate try/session: a power-stats failure should never roll back
        # the crisis/news/economic sync above.
        try:
            power_session = Session()
            try:
                DataAggregator.sync_actor_power_stats(power_session)
                power_session.commit()
            finally:
                power_session.close()
        except Exception as e:
            logger.error(f"Actor power-stats sync error: {e}")

    @staticmethod
    def sync_actor_power_stats(session):
        """Derive Actor.economic_power from real WorldBank GDP data already
        synced into EconomicData (log-scaled — GDP spans orders of magnitude,
        so a linear 0-100 scale would flatten every actor but the single
        largest economy near zero — then normalized 0-100 across whichever
        actors have real data this run).

        military_power/political_influence/technological_capability have no
        real data source anywhere in this app, so every actor's values are
        explicitly cleared to None on every run rather than left at a
        fabricated number — this also self-heals any actor row inserted
        before the Column-level default=50 was removed from the model.
        """
        actors = session.query(Actor).all()
        if not actors:
            return

        import math
        gdps = {}
        for actor in actors:
            actor.military_power = None
            actor.political_influence = None
            actor.technological_capability = None

            wb_code = ACTOR_WB_COUNTRY_OVERRIDES.get(actor.id, actor.id)
            econ = (session.query(EconomicData)
                    .filter(EconomicData.country_code == wb_code)
                    .order_by(EconomicData.year.desc())
                    .first())
            if econ and econ.gdp and econ.gdp > 0:
                gdps[actor.id] = econ.gdp
            else:
                actor.economic_power = None

        if gdps:
            log_gdps = {aid: math.log10(g) for aid, g in gdps.items()}
            lo, hi = min(log_gdps.values()), max(log_gdps.values())
            span = (hi - lo) or 1
            for actor in actors:
                if actor.id in log_gdps:
                    actor.economic_power = round(5 + 90 * (log_gdps[actor.id] - lo) / span)

        logger.info(f"Updated power stats for {len(actors)} actors ({len(gdps)} with real GDP data)")

    @staticmethod
    def snapshot_severity_history(session):
        """Record current severity for every active crisis. Called once per
        scheduled_sync() run (hourly) so analyze_escalation() has a real,
        growing time series instead of the fabricated pseudo-history it used
        to generate. A flat sequence of readings is a legitimate "stable"
        signal, not a gap — every active crisis gets one row per run
        regardless of whether its severity actually changed.
        """
        crises = session.query(Crisis).filter(Crisis.is_active == True).all()
        now = datetime.utcnow()
        for c in crises:
            session.add(CrisisSnapshot(crisis_id=c.id, severity=c.severity, recorded_at=now))
        logger.info(f"Recorded {len(crises)} severity snapshots")

    @staticmethod
    def _upsert_batch(session, candidates, source, report=None):
        """Run one connector's candidates through the event pipeline and
        store each resulting event: update the same id, merge into a
        matching active event already stored (same report URL, or the same
        event per event_pipeline.dedup), or insert. Returns the
        PipelineResult with .stored = {'inserted', 'updated', 'merged'}."""
        result = event_pipeline.process_batch(candidates, source, report=report)
        result.stored = {'inserted': 0, 'updated': 0, 'merged': 0}
        now = datetime.utcnow()
        for crisis_data, sources, meta in zip(result.kept, result.sources, result.metas):
            try:
                outcome = DataAggregator._store_event(session, crisis_data, sources, meta, now)
                result.stored[outcome] += 1
            except Exception as e:
                logger.error(f"Error storing crisis {crisis_data.get('id')}: {e}")
        return result

    @staticmethod
    def _store_event(session, crisis_data, sources, meta, now):
        """Store one pipeline event. Returns 'inserted', 'updated' or 'merged'."""
        from event_pipeline.dedup import find_existing, source_priority

        existing = session.get(Crisis, crisis_data['id'])
        if existing is not None:
            # Same report seen again: refresh it (and revive it if expired).
            for key, value in crisis_data.items():
                setattr(existing, key, value)
            outcome, row = 'updated', existing
        else:
            row = find_existing(session, crisis_data, meta, sources)
            if row is None:
                row = Crisis(**crisis_data)
                session.add(row)
                outcome = 'inserted'
            else:
                # Another report of an event we already have: fold it in
                # without letting a weaker report overwrite a better one.
                precision_rank = {'point': 4, 'city': 3, 'region': 2, 'country': 1}
                if precision_rank.get(crisis_data.get('location_precision'), 0) > \
                        precision_rank.get(row.location_precision, 0):
                    for key in ('latitude', 'longitude', 'country', 'country_code',
                                'location_precision', 'location_confidence'):
                        if crisis_data.get(key) is not None:
                            setattr(row, key, crisis_data[key])
                if crisis_data.get('title') and not meta.get('title_synthesized') and \
                        source_priority(crisis_data.get('source'), meta.get('outlet')) > source_priority(row.source):
                    row.title = crisis_data['title']
                if (crisis_data.get('severity') or 0) > (row.severity or 0):
                    row.severity = crisis_data['severity']
                if crisis_data.get('date_start') and row.date_start and crisis_data['date_start'] < row.date_start:
                    row.date_start = crisis_data['date_start']
                outcome = 'merged'

        row.is_active = True
        row.last_seen_at = now
        known = {key for (key,) in session.query(CrisisSource.url_key).filter(CrisisSource.crisis_id == row.id)}
        for record in sources:
            if record['url_key'] not in known:
                known.add(record['url_key'])
                session.add(CrisisSource(crisis_id=row.id, **record))
        row.source_count = max(len(known), 1)
        return outcome

    @staticmethod
    def expire_stale(session, now=None):
        """Deactivate (never delete) events no sync has reported for their
        source's TTL (config/event_filters.json -> lifecycle). Curated,
        sample, upcoming and human-verified rows are exempt. Rows from
        before last_seen_at existed fall back to date_updated."""
        from sqlalchemy import func, or_
        cfg = get_config().get('lifecycle', {})
        now = now or datetime.utcnow()
        expired = 0
        for prefix, days in cfg.get('ttl_days', {}).items():
            cutoff = now - timedelta(days=days)
            source_filter = Crisis.source.like(prefix + '%') if prefix.endswith('_') else Crisis.source == prefix
            rows = (session.query(Crisis)
                    .filter(Crisis.is_active == True,  # noqa: E712
                            source_filter,
                            ~Crisis.source.in_(cfg.get('exempt_sources', [])),
                            or_(Crisis.status.is_(None), Crisis.status != 'upcoming'),
                            or_(Crisis.is_verified.is_(None), Crisis.is_verified == False),  # noqa: E712
                            func.coalesce(Crisis.last_seen_at, Crisis.date_updated, Crisis.date_start) < cutoff)
                    .all())
            for row in rows:
                row.is_active = False
            expired += len(rows)
        if expired:
            logger.info(f"Deactivated {expired} stale crises")
        return expired

    @staticmethod
    def _upsert_crisis(session, crisis_data):
        """Insert or update a crisis by id (seed/sample data paths)."""
        try:
            existing = session.query(Crisis).filter(Crisis.id == crisis_data['id']).first()

            if existing:
                for key, value in crisis_data.items():
                    setattr(existing, key, value)
            else:
                crisis = Crisis(**crisis_data)
                session.add(crisis)

        except Exception as e:
            logger.error(f"Error upserting crisis: {e}")

    @staticmethod
    def _upsert_news(session, news_data):
        """Insert or update news article"""
        try:
            existing = session.query(News).filter(News.id == news_data['id']).first()

            if existing:
                for key, value in news_data.items():
                    setattr(existing, key, value)
            else:
                news = News(**news_data)
                session.add(news)

        except Exception as e:
            logger.error(f"Error upserting news: {e}")

    @staticmethod
    def _upsert_economic(session, econ_data):
        """Insert or update economic data"""
        try:
            existing = session.query(EconomicData).filter(
                EconomicData.id == econ_data['id']
            ).first()

            if existing:
                for key, value in econ_data.items():
                    setattr(existing, key, value)
            else:
                econ = EconomicData(**econ_data)
                session.add(econ)

        except Exception as e:
            logger.error(f"Error upserting economic data: {e}")


# Initialize actors
def init_actors():
    """Populate core actors.

    `id` is the actor's real ISO 3166-1 alpha-2 country code wherever one
    exists (WorldBankConnector.derive_country_codes relies on this to pull
    real GDP data per actor) — the only two exceptions are 'EU' (a real
    World Bank aggregate code, not a country) and 'NK' (kept for readability;
    translated to the real code 'KP' via ACTOR_WB_COUNTRY_OVERRIDES wherever
    a WorldBank/ISO code is needed). `is_nuclear` reflects real, publicly
    documented nuclear-weapon status (the five NPT nuclear-weapon states
    plus the four widely-acknowledged states outside the NPT) — never a
    guess. No power-stat fields are set here: economic_power is derived from
    real GDP by DataAggregator.sync_actor_power_stats once WorldBank data
    exists for the actor; the other three have no real source and stay None.
    """
    session = Session()

    actors_data = [
        # ── Original core roster ──────────────────────────────────────────
        {'id': 'US', 'name': 'United States', 'region': 'North America', 'latitude': 38.9072, 'longitude': -77.0369, 'color': '#4488ff', 'is_nuclear': True},
        {'id': 'CN', 'name': 'China', 'region': 'East Asia', 'latitude': 39.9042, 'longitude': 116.4074, 'color': '#ff4444', 'is_nuclear': True},
        {'id': 'RU', 'name': 'Russia', 'region': 'Eastern Europe / Eurasia', 'latitude': 55.7558, 'longitude': 37.6173, 'color': '#ff9933', 'is_nuclear': True},
        {'id': 'EU', 'name': 'European Union', 'region': 'Europe', 'latitude': 50.8503, 'longitude': 4.3517, 'color': '#88ccff', 'is_nuclear': False},
        {'id': 'IN', 'name': 'India', 'region': 'South Asia', 'latitude': 28.6139, 'longitude': 77.2090, 'color': '#ff7744', 'is_nuclear': True},
        {'id': 'IR', 'name': 'Iran', 'region': 'Middle East', 'latitude': 35.6892, 'longitude': 51.3890, 'color': '#cc44ff', 'is_nuclear': False},
        {'id': 'IL', 'name': 'Israel', 'region': 'Middle East', 'latitude': 31.7683, 'longitude': 35.2137, 'color': '#4488ff', 'is_nuclear': True},
        {'id': 'NK', 'name': 'North Korea', 'region': 'East Asia', 'latitude': 39.0392, 'longitude': 125.7625, 'color': '#ff4444', 'is_nuclear': True},

        # ── Major Western / NATO powers ────────────────────────────────────
        {'id': 'GB', 'name': 'United Kingdom', 'region': 'Europe', 'latitude': 51.5074, 'longitude': -0.1278, 'color': '#4488ff', 'is_nuclear': True},
        {'id': 'FR', 'name': 'France', 'region': 'Europe', 'latitude': 48.8566, 'longitude': 2.3522, 'color': '#5599ff', 'is_nuclear': True},
        {'id': 'DE', 'name': 'Germany', 'region': 'Europe', 'latitude': 52.5200, 'longitude': 13.4050, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'IT', 'name': 'Italy', 'region': 'Europe', 'latitude': 41.9028, 'longitude': 12.4964, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'ES', 'name': 'Spain', 'region': 'Europe', 'latitude': 40.4168, 'longitude': -3.7038, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'NL', 'name': 'Netherlands', 'region': 'Europe', 'latitude': 52.3676, 'longitude': 4.9041, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'PL', 'name': 'Poland', 'region': 'Europe', 'latitude': 52.2297, 'longitude': 21.0122, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'RO', 'name': 'Romania', 'region': 'Europe', 'latitude': 44.4268, 'longitude': 26.1025, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'GR', 'name': 'Greece', 'region': 'Europe', 'latitude': 37.9838, 'longitude': 23.7275, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'SE', 'name': 'Sweden', 'region': 'Europe', 'latitude': 59.3293, 'longitude': 18.0686, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'FI', 'name': 'Finland', 'region': 'Europe', 'latitude': 60.1699, 'longitude': 24.9384, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'NO', 'name': 'Norway', 'region': 'Europe', 'latitude': 59.9139, 'longitude': 10.7522, 'color': '#66aaff', 'is_nuclear': False},
        {'id': 'CH', 'name': 'Switzerland', 'region': 'Europe', 'latitude': 46.9480, 'longitude': 7.4474, 'color': '#99bbee', 'is_nuclear': False},
        {'id': 'CA', 'name': 'Canada', 'region': 'North America', 'latitude': 45.4215, 'longitude': -75.6972, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'AU', 'name': 'Australia', 'region': 'Oceania', 'latitude': -35.2809, 'longitude': 149.1300, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'NZ', 'name': 'New Zealand', 'region': 'Oceania', 'latitude': -41.2865, 'longitude': 174.7762, 'color': '#4488ff', 'is_nuclear': False},

        # ── East / South / Southeast Asia ──────────────────────────────────
        {'id': 'JP', 'name': 'Japan', 'region': 'East Asia', 'latitude': 35.6762, 'longitude': 139.6503, 'color': '#ff6666', 'is_nuclear': False},
        {'id': 'KR', 'name': 'South Korea', 'region': 'East Asia', 'latitude': 37.5665, 'longitude': 126.9780, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'TW', 'name': 'Taiwan', 'region': 'East Asia', 'latitude': 25.0330, 'longitude': 121.5654, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'PK', 'name': 'Pakistan', 'region': 'South Asia', 'latitude': 33.6844, 'longitude': 73.0479, 'color': '#88aa44', 'is_nuclear': True},
        {'id': 'AF', 'name': 'Afghanistan', 'region': 'South Asia', 'latitude': 34.5553, 'longitude': 69.2075, 'color': '#997744', 'is_nuclear': False},
        {'id': 'BD', 'name': 'Bangladesh', 'region': 'South Asia', 'latitude': 23.8103, 'longitude': 90.4125, 'color': '#88aa44', 'is_nuclear': False},
        {'id': 'MM', 'name': 'Myanmar', 'region': 'Southeast Asia', 'latitude': 19.7633, 'longitude': 96.0785, 'color': '#aa8844', 'is_nuclear': False},
        {'id': 'VN', 'name': 'Vietnam', 'region': 'Southeast Asia', 'latitude': 21.0285, 'longitude': 105.8542, 'color': '#ff5555', 'is_nuclear': False},
        {'id': 'TH', 'name': 'Thailand', 'region': 'Southeast Asia', 'latitude': 13.7563, 'longitude': 100.5018, 'color': '#88bb66', 'is_nuclear': False},
        {'id': 'PH', 'name': 'Philippines', 'region': 'Southeast Asia', 'latitude': 14.5995, 'longitude': 120.9842, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'ID', 'name': 'Indonesia', 'region': 'Southeast Asia', 'latitude': -6.2088, 'longitude': 106.8456, 'color': '#99bb55', 'is_nuclear': False},
        {'id': 'MY', 'name': 'Malaysia', 'region': 'Southeast Asia', 'latitude': 3.1390, 'longitude': 101.6869, 'color': '#99bb55', 'is_nuclear': False},
        {'id': 'SG', 'name': 'Singapore', 'region': 'Southeast Asia', 'latitude': 1.3521, 'longitude': 103.8198, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'KZ', 'name': 'Kazakhstan', 'region': 'Eastern Europe / Eurasia', 'latitude': 51.1694, 'longitude': 71.4491, 'color': '#dd9944', 'is_nuclear': False},

        # ── Middle East / North Africa ──────────────────────────────────────
        {'id': 'SA', 'name': 'Saudi Arabia', 'region': 'Middle East', 'latitude': 24.7136, 'longitude': 46.6753, 'color': '#66cc66', 'is_nuclear': False},
        {'id': 'TR', 'name': 'Turkey', 'region': 'Middle East', 'latitude': 39.9334, 'longitude': 32.8597, 'color': '#dd6644', 'is_nuclear': False},
        {'id': 'EG', 'name': 'Egypt', 'region': 'North Africa', 'latitude': 30.0444, 'longitude': 31.2357, 'color': '#ddaa44', 'is_nuclear': False},
        {'id': 'IQ', 'name': 'Iraq', 'region': 'Middle East', 'latitude': 33.3152, 'longitude': 44.3661, 'color': '#cc8844', 'is_nuclear': False},
        {'id': 'SY', 'name': 'Syria', 'region': 'Middle East', 'latitude': 33.5138, 'longitude': 36.2765, 'color': '#cc44ff', 'is_nuclear': False},
        {'id': 'YE', 'name': 'Yemen', 'region': 'Middle East', 'latitude': 15.3694, 'longitude': 44.1910, 'color': '#996633', 'is_nuclear': False},
        {'id': 'LB', 'name': 'Lebanon', 'region': 'Middle East', 'latitude': 33.8938, 'longitude': 35.5018, 'color': '#cc44ff', 'is_nuclear': False},
        {'id': 'JO', 'name': 'Jordan', 'region': 'Middle East', 'latitude': 31.9454, 'longitude': 35.9284, 'color': '#66cc66', 'is_nuclear': False},
        {'id': 'QA', 'name': 'Qatar', 'region': 'Middle East', 'latitude': 25.2854, 'longitude': 51.5310, 'color': '#66cc66', 'is_nuclear': False},
        {'id': 'AE', 'name': 'United Arab Emirates', 'region': 'Middle East', 'latitude': 24.4539, 'longitude': 54.3773, 'color': '#66cc66', 'is_nuclear': False},
        {'id': 'LY', 'name': 'Libya', 'region': 'North Africa', 'latitude': 32.8872, 'longitude': 13.1913, 'color': '#996633', 'is_nuclear': False},
        {'id': 'DZ', 'name': 'Algeria', 'region': 'North Africa', 'latitude': 36.7538, 'longitude': 3.0588, 'color': '#dd9944', 'is_nuclear': False},
        {'id': 'MA', 'name': 'Morocco', 'region': 'North Africa', 'latitude': 34.0209, 'longitude': -6.8417, 'color': '#dd9944', 'is_nuclear': False},

        # ── Sub-Saharan Africa ───────────────────────────────────────────
        {'id': 'ZA', 'name': 'South Africa', 'region': 'Sub-Saharan Africa', 'latitude': -25.7461, 'longitude': 28.1881, 'color': '#44aa88', 'is_nuclear': False},
        {'id': 'NG', 'name': 'Nigeria', 'region': 'Sub-Saharan Africa', 'latitude': 9.0765, 'longitude': 7.3986, 'color': '#44aa88', 'is_nuclear': False},
        {'id': 'ET', 'name': 'Ethiopia', 'region': 'Sub-Saharan Africa', 'latitude': 9.0250, 'longitude': 38.7469, 'color': '#44aa88', 'is_nuclear': False},
        {'id': 'SD', 'name': 'Sudan', 'region': 'North Africa', 'latitude': 15.5007, 'longitude': 32.5599, 'color': '#996633', 'is_nuclear': False},
        {'id': 'KE', 'name': 'Kenya', 'region': 'Sub-Saharan Africa', 'latitude': -1.2921, 'longitude': 36.8219, 'color': '#44aa88', 'is_nuclear': False},
        {'id': 'CD', 'name': 'DR Congo', 'region': 'Sub-Saharan Africa', 'latitude': -4.4419, 'longitude': 15.2663, 'color': '#996633', 'is_nuclear': False},

        # ── Americas ──────────────────────────────────────────────────────
        {'id': 'MX', 'name': 'Mexico', 'region': 'Latin America', 'latitude': 19.4326, 'longitude': -99.1332, 'color': '#dd8844', 'is_nuclear': False},
        {'id': 'BR', 'name': 'Brazil', 'region': 'Latin America', 'latitude': -15.8267, 'longitude': -47.9218, 'color': '#66bb44', 'is_nuclear': False},
        {'id': 'AR', 'name': 'Argentina', 'region': 'Latin America', 'latitude': -34.6037, 'longitude': -58.3816, 'color': '#77bbdd', 'is_nuclear': False},
        {'id': 'CO', 'name': 'Colombia', 'region': 'Latin America', 'latitude': 4.7110, 'longitude': -74.0721, 'color': '#ddcc44', 'is_nuclear': False},
        {'id': 'VE', 'name': 'Venezuela', 'region': 'Latin America', 'latitude': 10.4806, 'longitude': -66.9036, 'color': '#dd6644', 'is_nuclear': False},
        {'id': 'CU', 'name': 'Cuba', 'region': 'Latin America', 'latitude': 23.1136, 'longitude': -82.3666, 'color': '#dd6644', 'is_nuclear': False},

        # ── Eastern Europe / Caucasus / Central Asia ────────────────────────
        {'id': 'UA', 'name': 'Ukraine', 'region': 'Eastern Europe / Eurasia', 'latitude': 50.4501, 'longitude': 30.5234, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'BY', 'name': 'Belarus', 'region': 'Eastern Europe / Eurasia', 'latitude': 53.9006, 'longitude': 27.5590, 'color': '#ff9933', 'is_nuclear': False},
        {'id': 'GE', 'name': 'Georgia', 'region': 'Eastern Europe / Eurasia', 'latitude': 41.7151, 'longitude': 44.8271, 'color': '#4488ff', 'is_nuclear': False},
        {'id': 'AM', 'name': 'Armenia', 'region': 'Eastern Europe / Eurasia', 'latitude': 40.1792, 'longitude': 44.4991, 'color': '#dd9944', 'is_nuclear': False},
        {'id': 'AZ', 'name': 'Azerbaijan', 'region': 'Eastern Europe / Eurasia', 'latitude': 40.4093, 'longitude': 49.8671, 'color': '#dd6644', 'is_nuclear': False},
    ]

    try:
        for actor_data in actors_data:
            existing = session.query(Actor).filter(Actor.id == actor_data['id']).first()
            if not existing:
                actor = Actor(**actor_data)
                session.add(actor)
            elif existing.region != actor_data.get('region'):
                # region is static curated truth (unlike power stats, which
                # are synced separately from real GDP data) — safe to
                # backfill onto an already-existing row without touching
                # anything else. This is what makes analyze_cascade()'s
                # affected_regions real instead of permanently [].
                existing.region = actor_data.get('region')

        session.commit()
        logger.info(f"Actors initialized ({len(actors_data)} in roster)")
    except Exception as e:
        session.rollback()
        logger.error(f"Error initializing actors: {e}")
    finally:
        session.close()


def init_relationships():
    """Populate core geopolitical relationships.

    All hand-curated from real, publicly known alliance/treaty/conflict
    structures (NATO/EU membership, defense treaties, active wars and
    territorial disputes) — never generated. This intentionally does not
    cover every pair among the ~68 actors in init_actors(): relationships
    have no API to pull from, so this is curation work landed incrementally.
    An actor with no relationship entry here simply doesn't participate in
    cascade traversal yet — that's an honest gap, not a bug (see
    analyze_cascade() in app.py).
    """
    session = Session()

    relationships_data = [
        # ── Original core relationships ───────────────────────────────────
        {'id': 'US-CN-conflict', 'actor_a': 'US', 'actor_b': 'CN', 'type': 'conflict', 'label': 'Strategic Rivalry / Tech War', 'strength': 85, 'stability': 40},
        {'id': 'US-RU-conflict', 'actor_a': 'US', 'actor_b': 'RU', 'type': 'conflict', 'label': 'Ukraine Proxy Conflict', 'strength': 80, 'stability': 35},
        {'id': 'CN-RU-alliance', 'actor_a': 'CN', 'actor_b': 'RU', 'type': 'alliance', 'label': 'No-Limits Partnership', 'strength': 75, 'stability': 60},
        {'id': 'US-EU-alliance', 'actor_a': 'US', 'actor_b': 'EU', 'type': 'alliance', 'label': 'NATO / Transatlantic Alliance', 'strength': 90, 'stability': 85},
        {'id': 'US-IL-alliance', 'actor_a': 'US', 'actor_b': 'IL', 'type': 'alliance', 'label': 'Defense Commitment', 'strength': 85, 'stability': 80},
        {'id': 'IR-RU-alliance', 'actor_a': 'IR', 'actor_b': 'RU', 'type': 'alliance', 'label': 'Weapons & Energy Cooperation', 'strength': 70, 'stability': 65},
        {'id': 'CN-IR-economic', 'actor_a': 'CN', 'actor_b': 'IR', 'type': 'economic', 'label': 'Oil & Infrastructure Investment', 'strength': 65, 'stability': 70},
        {'id': 'US-IN-alliance', 'actor_a': 'US', 'actor_b': 'IN', 'type': 'alliance', 'label': 'Quad Partnership', 'strength': 60, 'stability': 70},
        {'id': 'CN-IN-tension', 'actor_a': 'CN', 'actor_b': 'IN', 'type': 'tension', 'label': 'Border Disputes / Rivalry', 'strength': 55, 'stability': 45},
        {'id': 'IR-IL-conflict', 'actor_a': 'IR', 'actor_b': 'IL', 'type': 'conflict', 'label': 'Direct Military Confrontation', 'strength': 90, 'stability': 30},
        {'id': 'NK-RU-alliance', 'actor_a': 'NK', 'actor_b': 'RU', 'type': 'alliance', 'label': 'Weapons Supply', 'strength': 50, 'stability': 55},
        {'id': 'NK-CN-economic', 'actor_a': 'NK', 'actor_b': 'CN', 'type': 'economic', 'label': 'Economic Lifeline', 'strength': 70, 'stability': 60},
        {'id': 'US-NK-conflict', 'actor_a': 'US', 'actor_b': 'NK', 'type': 'conflict', 'label': 'Nuclear Standoff', 'strength': 85, 'stability': 50},

        # ── NATO alliance ties (real member states → US) ────────────────────
        {'id': 'US-GB-alliance', 'actor_a': 'US', 'actor_b': 'GB', 'type': 'alliance', 'label': 'Special Relationship / NATO', 'strength': 90, 'stability': 90},
        {'id': 'US-FR-alliance', 'actor_a': 'US', 'actor_b': 'FR', 'type': 'alliance', 'label': 'NATO Alliance', 'strength': 80, 'stability': 80},
        {'id': 'US-DE-alliance', 'actor_a': 'US', 'actor_b': 'DE', 'type': 'alliance', 'label': 'NATO Alliance', 'strength': 82, 'stability': 82},
        {'id': 'US-PL-alliance', 'actor_a': 'US', 'actor_b': 'PL', 'type': 'alliance', 'label': 'NATO Eastern Flank Defense', 'strength': 80, 'stability': 78},
        {'id': 'US-TR-alliance', 'actor_a': 'US', 'actor_b': 'TR', 'type': 'alliance', 'label': 'NATO Alliance (Strained)', 'strength': 55, 'stability': 50},
        {'id': 'US-NO-alliance', 'actor_a': 'US', 'actor_b': 'NO', 'type': 'alliance', 'label': 'NATO / Arctic Security', 'strength': 78, 'stability': 85},
        {'id': 'US-RO-alliance', 'actor_a': 'US', 'actor_b': 'RO', 'type': 'alliance', 'label': 'NATO Black Sea Security', 'strength': 75, 'stability': 78},
        {'id': 'US-IT-alliance', 'actor_a': 'US', 'actor_b': 'IT', 'type': 'alliance', 'label': 'NATO Alliance', 'strength': 78, 'stability': 82},
        {'id': 'US-CA-alliance', 'actor_a': 'US', 'actor_b': 'CA', 'type': 'alliance', 'label': 'NATO / NORAD', 'strength': 88, 'stability': 90},

        # ── EU intra-membership ties ─────────────────────────────────────
        {'id': 'DE-FR-alliance', 'actor_a': 'DE', 'actor_b': 'FR', 'type': 'alliance', 'label': 'EU Franco-German Axis', 'strength': 85, 'stability': 88},
        {'id': 'DE-IT-alliance', 'actor_a': 'DE', 'actor_b': 'IT', 'type': 'alliance', 'label': 'EU Membership', 'strength': 70, 'stability': 75},
        {'id': 'DE-NL-alliance', 'actor_a': 'DE', 'actor_b': 'NL', 'type': 'alliance', 'label': 'EU Membership', 'strength': 72, 'stability': 82},
        {'id': 'DE-PL-alliance', 'actor_a': 'DE', 'actor_b': 'PL', 'type': 'alliance', 'label': 'EU Membership', 'strength': 65, 'stability': 68},
        {'id': 'FR-ES-alliance', 'actor_a': 'FR', 'actor_b': 'ES', 'type': 'alliance', 'label': 'EU Membership', 'strength': 68, 'stability': 78},
        {'id': 'SE-FI-alliance', 'actor_a': 'SE', 'actor_b': 'FI', 'type': 'alliance', 'label': 'Nordic Defense Cooperation / NATO', 'strength': 80, 'stability': 85},

        # ── Indo-Pacific security architecture ───────────────────────────
        {'id': 'US-JP-alliance', 'actor_a': 'US', 'actor_b': 'JP', 'type': 'alliance', 'label': 'US-Japan Security Treaty', 'strength': 88, 'stability': 88},
        {'id': 'US-KR-alliance', 'actor_a': 'US', 'actor_b': 'KR', 'type': 'alliance', 'label': 'Mutual Defense Treaty', 'strength': 88, 'stability': 85},
        {'id': 'US-AU-alliance', 'actor_a': 'US', 'actor_b': 'AU', 'type': 'alliance', 'label': 'ANZUS / AUKUS', 'strength': 85, 'stability': 88},
        {'id': 'US-NZ-alliance', 'actor_a': 'US', 'actor_b': 'NZ', 'type': 'alliance', 'label': 'ANZUS (Historical)', 'strength': 65, 'stability': 82},
        {'id': 'US-PH-alliance', 'actor_a': 'US', 'actor_b': 'PH', 'type': 'alliance', 'label': 'Mutual Defense Treaty', 'strength': 72, 'stability': 70},
        {'id': 'US-TW-alliance', 'actor_a': 'US', 'actor_b': 'TW', 'type': 'alliance', 'label': 'Taiwan Relations Act / Arms Support', 'strength': 75, 'stability': 60},
        {'id': 'CN-TW-conflict', 'actor_a': 'CN', 'actor_b': 'TW', 'type': 'conflict', 'label': 'Cross-Strait Tensions', 'strength': 88, 'stability': 35},
        {'id': 'JP-CN-tension', 'actor_a': 'JP', 'actor_b': 'CN', 'type': 'tension', 'label': 'East China Sea / Senkaku Dispute', 'strength': 65, 'stability': 45},
        {'id': 'JP-KR-tension', 'actor_a': 'JP', 'actor_b': 'KR', 'type': 'tension', 'label': 'Historical Grievances / Security Cooperation', 'strength': 45, 'stability': 65},
        {'id': 'KR-NK-conflict', 'actor_a': 'KR', 'actor_b': 'NK', 'type': 'conflict', 'label': 'Korean Peninsula Standoff', 'strength': 90, 'stability': 40},
        {'id': 'CN-PK-alliance', 'actor_a': 'CN', 'actor_b': 'PK', 'type': 'alliance', 'label': 'All-Weather Strategic Partnership', 'strength': 82, 'stability': 78},
        {'id': 'IN-PK-conflict', 'actor_a': 'IN', 'actor_b': 'PK', 'type': 'conflict', 'label': 'Kashmir Dispute', 'strength': 88, 'stability': 30},
        {'id': 'IN-RU-alliance', 'actor_a': 'IN', 'actor_b': 'RU', 'type': 'alliance', 'label': 'Defense & Energy Cooperation', 'strength': 65, 'stability': 72},
        {'id': 'PK-AF-tension', 'actor_a': 'PK', 'actor_b': 'AF', 'type': 'tension', 'label': 'Durand Line Border Tensions', 'strength': 62, 'stability': 40},
        {'id': 'CN-VN-tension', 'actor_a': 'CN', 'actor_b': 'VN', 'type': 'tension', 'label': 'South China Sea Dispute', 'strength': 55, 'stability': 50},
        {'id': 'CN-PH-tension', 'actor_a': 'CN', 'actor_b': 'PH', 'type': 'tension', 'label': 'South China Sea Dispute', 'strength': 60, 'stability': 45},
        {'id': 'MM-CN-economic', 'actor_a': 'MM', 'actor_b': 'CN', 'type': 'economic', 'label': 'Economic & Political Backing', 'strength': 60, 'stability': 55},

        # ── Middle East / North Africa ────────────────────────────────────
        {'id': 'SA-IR-conflict', 'actor_a': 'SA', 'actor_b': 'IR', 'type': 'conflict', 'label': 'Regional Rivalry / Proxy Conflicts', 'strength': 80, 'stability': 40},
        {'id': 'US-SA-alliance', 'actor_a': 'US', 'actor_b': 'SA', 'type': 'alliance', 'label': 'Defense & Oil Partnership', 'strength': 75, 'stability': 70},
        {'id': 'US-EG-alliance', 'actor_a': 'US', 'actor_b': 'EG', 'type': 'alliance', 'label': 'Camp David Accords / Military Aid', 'strength': 68, 'stability': 75},
        {'id': 'US-QA-alliance', 'actor_a': 'US', 'actor_b': 'QA', 'type': 'alliance', 'label': 'Al Udeid Air Base / Defense Ties', 'strength': 72, 'stability': 78},
        {'id': 'US-AE-alliance', 'actor_a': 'US', 'actor_b': 'AE', 'type': 'alliance', 'label': 'Defense & Abraham Accords', 'strength': 74, 'stability': 78},
        {'id': 'US-JO-alliance', 'actor_a': 'US', 'actor_b': 'JO', 'type': 'alliance', 'label': 'Major Non-NATO Ally', 'strength': 70, 'stability': 80},
        {'id': 'IL-JO-alliance', 'actor_a': 'IL', 'actor_b': 'JO', 'type': 'alliance', 'label': 'Israel-Jordan Peace Treaty', 'strength': 55, 'stability': 68},
        {'id': 'IL-LB-conflict', 'actor_a': 'IL', 'actor_b': 'LB', 'type': 'conflict', 'label': 'Southern Lebanon Conflict (Hezbollah)', 'strength': 82, 'stability': 30},
        {'id': 'IL-SY-conflict', 'actor_a': 'IL', 'actor_b': 'SY', 'type': 'conflict', 'label': 'Golan Heights / Ongoing Strikes', 'strength': 70, 'stability': 35},
        {'id': 'IR-SY-alliance', 'actor_a': 'IR', 'actor_b': 'SY', 'type': 'alliance', 'label': 'Axis of Resistance', 'strength': 65, 'stability': 45},
        {'id': 'IR-LB-alliance', 'actor_a': 'IR', 'actor_b': 'LB', 'type': 'alliance', 'label': 'Hezbollah Sponsorship', 'strength': 72, 'stability': 50},
        {'id': 'IR-IQ-alliance', 'actor_a': 'IR', 'actor_b': 'IQ', 'type': 'alliance', 'label': 'Shia Political & Militia Ties', 'strength': 68, 'stability': 55},
        {'id': 'SA-YE-conflict', 'actor_a': 'SA', 'actor_b': 'YE', 'type': 'conflict', 'label': 'Saudi-Led Intervention (Houthi War)', 'strength': 78, 'stability': 35},
        {'id': 'IR-YE-alliance', 'actor_a': 'IR', 'actor_b': 'YE', 'type': 'alliance', 'label': 'Houthi Weapons Support', 'strength': 65, 'stability': 45},
        {'id': 'MA-DZ-tension', 'actor_a': 'MA', 'actor_b': 'DZ', 'type': 'tension', 'label': 'Western Sahara Dispute', 'strength': 60, 'stability': 40},
        {'id': 'TR-GR-tension', 'actor_a': 'TR', 'actor_b': 'GR', 'type': 'tension', 'label': 'Aegean Sea / Cyprus Disputes', 'strength': 58, 'stability': 50},
        {'id': 'TR-SY-tension', 'actor_a': 'TR', 'actor_b': 'SY', 'type': 'tension', 'label': 'Border Security / Kurdish Militias', 'strength': 65, 'stability': 40},

        # ── Russia / post-Soviet space ────────────────────────────────────
        {'id': 'RU-UA-conflict', 'actor_a': 'RU', 'actor_b': 'UA', 'type': 'conflict', 'label': 'Full-Scale War', 'strength': 98, 'stability': 15},
        {'id': 'RU-BY-alliance', 'actor_a': 'RU', 'actor_b': 'BY', 'type': 'alliance', 'label': 'Union State', 'strength': 85, 'stability': 75},
        {'id': 'RU-GE-conflict', 'actor_a': 'RU', 'actor_b': 'GE', 'type': 'conflict', 'label': 'Frozen Conflict (Abkhazia/S. Ossetia)', 'strength': 60, 'stability': 40},
        {'id': 'RU-KZ-economic', 'actor_a': 'RU', 'actor_b': 'KZ', 'type': 'economic', 'label': 'Eurasian Economic Union Ties', 'strength': 62, 'stability': 70},
        {'id': 'RU-AM-alliance', 'actor_a': 'RU', 'actor_b': 'AM', 'type': 'alliance', 'label': 'CSTO Security Guarantee', 'strength': 58, 'stability': 60},
        {'id': 'AZ-AM-conflict', 'actor_a': 'AZ', 'actor_b': 'AM', 'type': 'conflict', 'label': 'Nagorno-Karabakh Conflict', 'strength': 75, 'stability': 35},
        {'id': 'UA-EU-alliance', 'actor_a': 'UA', 'actor_b': 'EU', 'type': 'alliance', 'label': 'EU Accession Track / Support', 'strength': 78, 'stability': 65},
        {'id': 'US-UA-alliance', 'actor_a': 'US', 'actor_b': 'UA', 'type': 'alliance', 'label': 'Military & Financial Aid', 'strength': 80, 'stability': 60},

        # ── Africa ────────────────────────────────────────────────────────
        {'id': 'ET-SD-tension', 'actor_a': 'ET', 'actor_b': 'SD', 'type': 'tension', 'label': 'Al-Fashaga Border Dispute', 'strength': 50, 'stability': 45},
        {'id': 'ZA-CN-economic', 'actor_a': 'ZA', 'actor_b': 'CN', 'type': 'economic', 'label': 'BRICS / Trade Partnership', 'strength': 58, 'stability': 72},
        {'id': 'NG-CN-economic', 'actor_a': 'NG', 'actor_b': 'CN', 'type': 'economic', 'label': 'Infrastructure Investment', 'strength': 55, 'stability': 68},

        # ── Americas ──────────────────────────────────────────────────────
        {'id': 'US-MX-economic', 'actor_a': 'US', 'actor_b': 'MX', 'type': 'economic', 'label': 'USMCA Trade Partnership', 'strength': 82, 'stability': 78},
        {'id': 'US-CO-alliance', 'actor_a': 'US', 'actor_b': 'CO', 'type': 'alliance', 'label': 'Major Non-NATO Ally', 'strength': 68, 'stability': 75},
        {'id': 'US-VE-conflict', 'actor_a': 'US', 'actor_b': 'VE', 'type': 'conflict', 'label': 'Sanctions Regime / Diplomatic Standoff', 'strength': 65, 'stability': 35},
        {'id': 'US-CU-conflict', 'actor_a': 'US', 'actor_b': 'CU', 'type': 'conflict', 'label': 'Cold War-Era Sanctions', 'strength': 55, 'stability': 55},
        {'id': 'CN-BR-economic', 'actor_a': 'CN', 'actor_b': 'BR', 'type': 'economic', 'label': 'BRICS / Trade Partnership', 'strength': 62, 'stability': 75},
        {'id': 'VE-CO-tension', 'actor_a': 'VE', 'actor_b': 'CO', 'type': 'tension', 'label': 'Border Migration Crisis', 'strength': 52, 'stability': 45},
        {'id': 'RU-VE-alliance', 'actor_a': 'RU', 'actor_b': 'VE', 'type': 'alliance', 'label': 'Political & Military Support', 'strength': 55, 'stability': 55},
        {'id': 'RU-CU-alliance', 'actor_a': 'RU', 'actor_b': 'CU', 'type': 'alliance', 'label': 'Historical Cold War Ties', 'strength': 45, 'stability': 60},
    ]

    try:
        for rel_data in relationships_data:
            existing = session.query(Relationship).filter(Relationship.id == rel_data['id']).first()
            if not existing:
                relationship = Relationship(**rel_data)
                session.add(relationship)

        session.commit()
        logger.info(f"Relationships initialized ({len(relationships_data)} in roster)")
    except Exception as e:
        session.rollback()
        logger.error(f"Error initializing relationships: {e}")
    finally:
        session.close()


_SCHEDULED_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'config', 'scheduled_events.json'
)


def init_scheduled_events():
    """Populate curated upcoming elections/referendums (config/scheduled_events.json).

    Unlike every other crisis type, these are known in advance rather than
    detected from news, so they come from a hand-maintained file instead of
    NewsBasedCrisisDetector. date_start is set to ingestion time (now) rather
    than the real future date, matching every other crisis row — the
    year-slider's filterByDateRange() in app.js matches by exact calendar
    year against date_start, so a true future date would make the pin
    invisible until that year arrives. date_scheduled carries the real date
    for display; status='upcoming' distinguishes it until it's flipped to
    'resolved' (e.g. via PATCH /api/crises/<id>) after it happens.
    """
    session = Session()

    try:
        with open(_SCHEDULED_EVENTS_PATH, 'r', encoding='utf-8') as f:
            events_data = json.load(f).get('events', [])
    except Exception as e:
        logger.error(f"Could not load {_SCHEDULED_EVENTS_PATH}: {e}")
        session.close()
        return

    try:
        for event in events_data:
            existing = session.query(Crisis).filter(Crisis.id == event['id']).first()
            if existing:
                continue

            crisis = Crisis(
                id=event['id'],
                type=event['type'],
                title=event['title'],
                country=event['country'],
                latitude=event['latitude'],
                longitude=event['longitude'],
                severity=event.get('severity', 50),
                confidence=100,
                date_start=datetime.utcnow(),
                date_scheduled=datetime.fromisoformat(event['date_scheduled']),
                status='upcoming',
                analysis=event.get('analysis', ''),
                source='CURATED',
            )
            session.add(crisis)

        session.commit()
        logger.info("Scheduled events initialized")
    except Exception as e:
        session.rollback()
        logger.error(f"Error initializing scheduled events: {e}")
    finally:
        session.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_actors()
    DataAggregator.sync_all_sources()
