"""
Data source connectors for real-world geopolitical data
"""
import requests
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from models import Crisis, News, Actor, Relationship, EconomicData, CrisisSnapshot, Session
import json
import logging
from dotenv import load_dotenv

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
NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"

# Optional: same AI-primary/static-fallback pattern app.py's anthropic_client
# already uses for briefings/history — here it drives real incident-level
# geocoding (see NominatimGeocoder / _extract_incident_location) instead of
# text generation. A separate client instance because this module has no
# dependency on app.py today and geocoding needs to keep working even if
# app.py's own client init ever changes.
try:
    from anthropic import Anthropic
    _geocode_ai_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except Exception:
    _geocode_ai_client = None

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
                'title': event.get('event_id_cnty', 'Unknown Event'),
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


class NominatimGeocoder:
    """
    Thin client for OpenStreetMap's free Nominatim geocoding API — resolves
    an arbitrary place name (a landmark, a national capital, an ad-hoc
    incident location) to real coordinates, no API key required. This is
    what makes precise pins possible for things the curated LOCATION_MAP
    below was never going to cover (the UN, the White House, a specific
    neighborhood a missile was heard over) without hand-maintaining an
    ever-growing landmark table.

    Nominatim's usage policy caps free use at 1 request/second and requires
    a real, descriptive User-Agent identifying the calling application —
    both enforced here, the same courtesy fetch_wikipedia_bilateral() (see
    app.py) already extends to Wikipedia's API.
    """
    _last_request_at = 0.0
    _cache = {}  # place name -> {'lat', 'lon', 'country'} or None, in-process

    @staticmethod
    def geocode(place_name):
        """Real (lat, lon, country) for `place_name`, or None if Nominatim
        has nothing for it or the request fails. Cached in-process by exact
        place name — the same landmark (the UN, the Kremlin) recurs across
        many articles over time, and repeating the network call for an
        identical string would just burn the shared rate limit."""
        if not place_name:
            return None
        key = place_name.strip().lower()
        if key in NominatimGeocoder._cache:
            return NominatimGeocoder._cache[key]

        import time
        elapsed = time.monotonic() - NominatimGeocoder._last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        NominatimGeocoder._last_request_at = time.monotonic()

        result = None
        try:
            response = requests.get(
                NOMINATIM_BASE,
                # accept-language=en: Nominatim otherwise replies in the
                # location's local language by default (e.g. country
                # "Россия" for Russia) — every other country name in this
                # app (the Actor roster, LOCATION_MAP) is English, and
                # analyze_cascade()'s initial-actor lookup matches
                # Crisis.country against Actor.name by exact string, so a
                # non-English country name here would silently never match.
                params={'q': place_name, 'format': 'json', 'addressdetails': 1, 'limit': 1, 'accept-language': 'en'},
                headers={'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data:
                match = data[0]
                result = {
                    'lat': float(match['lat']),
                    'lon': float(match['lon']),
                    'country': (match.get('address') or {}).get('country'),
                }
        except Exception as e:
            logger.warning(f"Nominatim geocode failed for '{place_name}': {e}")

        NominatimGeocoder._cache[key] = result
        return result


def _extract_incident_location(text):
    """
    Ask Claude for the single most specific real-world location (a
    building, landmark, city, or region) genuinely associated with the
    EVENT this article describes — not just any place named in passing.
    Returns a location name string, or None when no ANTHROPIC_API_KEY is
    configured, the model finds no clear location, or anything goes wrong.
    None here always means "fall back to LOCATION_MAP city-matching below"
    — never a guessed location.
    """
    if not _geocode_ai_client or not _geocode_ai_client.api_key:
        return None
    try:
        message = _geocode_ai_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=40,
            messages=[{
                "role": "user",
                "content": (
                    "What is the single most specific real-world location "
                    "(a building, landmark, city, or region) genuinely "
                    "associated with the main event in this news text — not "
                    "just any place mentioned in passing? Reply with ONLY "
                    "the location name (e.g. \"United Nations Headquarters, "
                    "New York\" or \"the Kremlin, Moscow\"), or reply with "
                    "exactly NONE if there is no clear location.\n\n"
                    f"Text: {text[:1000]}"
                ),
            }],
        )
        answer = message.content[0].text.strip()
        if not answer or answer.upper() == 'NONE':
            return None
        return answer
    except Exception as e:
        logger.warning(f"AI location extraction failed: {e}")
        return None


class NewsBasedCrisisDetector:
    """Extract real crises from news articles"""

    # CITIES ONLY — exact coordinates for city names found in article text
    # These are searched against article title + description
    # NO country fallbacks — only show events where a specific city is mentioned
    LOCATION_MAP = {
        # Middle East
        'tehran': {'lat': 35.6892, 'lon': 51.3890, 'country': 'Iran'},
        'isfahan': {'lat': 32.6546, 'lon': 51.6680, 'country': 'Iran'},
        'shiraz': {'lat': 29.5918, 'lon': 52.5837, 'country': 'Iran'},
        'mashhad': {'lat': 36.2605, 'lon': 59.5007, 'country': 'Iran'},
        'jerusalem': {'lat': 31.7683, 'lon': 35.2137, 'country': 'Israel'},
        'tel aviv': {'lat': 32.0853, 'lon': 34.7818, 'country': 'Israel'},
        'haifa': {'lat': 32.7940, 'lon': 34.9896, 'country': 'Israel'},
        'gaza': {'lat': 31.5017, 'lon': 34.4668, 'country': 'Palestine'},
        'ramallah': {'lat': 31.9038, 'lon': 35.2034, 'country': 'Palestine'},
        'beirut': {'lat': 33.8938, 'lon': 35.5018, 'country': 'Lebanon'},
        'damascus': {'lat': 33.5138, 'lon': 36.2765, 'country': 'Syria'},
        'aleppo': {'lat': 36.2021, 'lon': 37.1343, 'country': 'Syria'},
        'baghdad': {'lat': 33.3152, 'lon': 44.3661, 'country': 'Iraq'},
        'mosul': {'lat': 36.3350, 'lon': 43.1189, 'country': 'Iraq'},
        'basra': {'lat': 30.5085, 'lon': 47.7804, 'country': 'Iraq'},
        'sanaa': {'lat': 15.3694, 'lon': 44.1910, 'country': 'Yemen'},
        'aden': {'lat': 12.7797, 'lon': 45.0095, 'country': 'Yemen'},
        'riyadh': {'lat': 24.7136, 'lon': 46.6753, 'country': 'Saudi Arabia'},
        'jeddah': {'lat': 21.5433, 'lon': 39.1728, 'country': 'Saudi Arabia'},
        'dubai': {'lat': 25.2048, 'lon': 55.2708, 'country': 'UAE'},
        'abu dhabi': {'lat': 24.4539, 'lon': 54.3773, 'country': 'UAE'},
        'ankara': {'lat': 39.9334, 'lon': 32.8597, 'country': 'Turkey'},
        'istanbul': {'lat': 41.0082, 'lon': 28.9784, 'country': 'Turkey'},
        'kabul': {'lat': 34.5553, 'lon': 69.2075, 'country': 'Afghanistan'},
        'islamabad': {'lat': 33.6844, 'lon': 73.0479, 'country': 'Pakistan'},
        'karachi': {'lat': 24.8607, 'lon': 67.0011, 'country': 'Pakistan'},
        'doha': {'lat': 25.2854, 'lon': 51.5310, 'country': 'Qatar'},
        'muscat': {'lat': 23.5880, 'lon': 58.3829, 'country': 'Oman'},
        'amman': {'lat': 31.9454, 'lon': 35.9284, 'country': 'Jordan'},
        'hormuz': {'lat': 26.5667, 'lon': 56.2667, 'country': 'Iran'},
        # Europe
        'moscow': {'lat': 55.7558, 'lon': 37.6173, 'country': 'Russia'},
        'st petersburg': {'lat': 59.9343, 'lon': 30.3351, 'country': 'Russia'},
        'kyiv': {'lat': 50.4501, 'lon': 30.5234, 'country': 'Ukraine'},
        'kharkiv': {'lat': 49.9935, 'lon': 36.2304, 'country': 'Ukraine'},
        'odesa': {'lat': 46.4825, 'lon': 30.7233, 'country': 'Ukraine'},
        'london': {'lat': 51.5074, 'lon': -0.1278, 'country': 'UK'},
        'paris': {'lat': 48.8566, 'lon': 2.3522, 'country': 'France'},
        'berlin': {'lat': 52.5200, 'lon': 13.4050, 'country': 'Germany'},
        'brussels': {'lat': 50.8503, 'lon': 4.3517, 'country': 'Belgium'},
        'warsaw': {'lat': 52.2297, 'lon': 21.0122, 'country': 'Poland'},
        'rome': {'lat': 41.9028, 'lon': 12.4964, 'country': 'Italy'},
        'madrid': {'lat': 40.4168, 'lon': -3.7038, 'country': 'Spain'},
        'stockholm': {'lat': 59.3293, 'lon': 18.0686, 'country': 'Sweden'},
        'helsinki': {'lat': 60.1699, 'lon': 24.9384, 'country': 'Finland'},
        'bucharest': {'lat': 44.4268, 'lon': 26.1025, 'country': 'Romania'},
        'belgrade': {'lat': 44.7866, 'lon': 20.4489, 'country': 'Serbia'},
        'baku': {'lat': 40.4093, 'lon': 49.8671, 'country': 'Azerbaijan'},
        'tbilisi': {'lat': 41.6938, 'lon': 44.8015, 'country': 'Georgia'},
        'minsk': {'lat': 53.9045, 'lon': 27.5615, 'country': 'Belarus'},
        # Asia-Pacific
        'beijing': {'lat': 39.9042, 'lon': 116.4074, 'country': 'China'},
        'shanghai': {'lat': 31.2304, 'lon': 121.4737, 'country': 'China'},
        'hong kong': {'lat': 22.3193, 'lon': 114.1694, 'country': 'China'},
        'taipei': {'lat': 25.0330, 'lon': 121.5654, 'country': 'Taiwan'},
        'tokyo': {'lat': 35.6762, 'lon': 139.6503, 'country': 'Japan'},
        'osaka': {'lat': 34.6937, 'lon': 135.5023, 'country': 'Japan'},
        'seoul': {'lat': 37.5665, 'lon': 126.9780, 'country': 'South Korea'},
        'pyongyang': {'lat': 39.0193, 'lon': 125.7581, 'country': 'North Korea'},
        'manila': {'lat': 14.5995, 'lon': 120.9842, 'country': 'Philippines'},
        'bangkok': {'lat': 13.7563, 'lon': 100.5018, 'country': 'Thailand'},
        'hanoi': {'lat': 21.0285, 'lon': 105.8542, 'country': 'Vietnam'},
        'ho chi minh': {'lat': 10.8231, 'lon': 106.6297, 'country': 'Vietnam'},
        'jakarta': {'lat': -6.2088, 'lon': 106.8456, 'country': 'Indonesia'},
        'kuala lumpur': {'lat': 3.1390, 'lon': 101.6869, 'country': 'Malaysia'},
        'singapore': {'lat': 1.3521, 'lon': 103.8198, 'country': 'Singapore'},
        'yangon': {'lat': 16.8661, 'lon': 96.1951, 'country': 'Myanmar'},
        'naypyidaw': {'lat': 19.7633, 'lon': 96.0785, 'country': 'Myanmar'},
        'new delhi': {'lat': 28.6139, 'lon': 77.2090, 'country': 'India'},
        'mumbai': {'lat': 19.0760, 'lon': 72.8777, 'country': 'India'},
        'islamabad': {'lat': 33.6844, 'lon': 73.0479, 'country': 'Pakistan'},
        'kathmandu': {'lat': 27.7172, 'lon': 85.3240, 'country': 'Nepal'},
        'colombo': {'lat': 6.9271, 'lon': 79.8612, 'country': 'Sri Lanka'},
        'dhaka': {'lat': 23.8103, 'lon': 90.4125, 'country': 'Bangladesh'},
        # Americas
        'washington dc': {'lat': 38.9072, 'lon': -77.0369, 'country': 'US'},
        'washington': {'lat': 38.9072, 'lon': -77.0369, 'country': 'US'},
        'new york': {'lat': 40.7128, 'lon': -74.0060, 'country': 'US'},
        'pentagon': {'lat': 38.8719, 'lon': -77.0563, 'country': 'US'},
        'los angeles': {'lat': 34.0522, 'lon': -118.2437, 'country': 'US'},
        'chicago': {'lat': 41.8781, 'lon': -87.6298, 'country': 'US'},
        'miami': {'lat': 25.7617, 'lon': -80.1918, 'country': 'US'},
        'ottawa': {'lat': 45.4215, 'lon': -75.6972, 'country': 'Canada'},
        'toronto': {'lat': 43.6532, 'lon': -79.3832, 'country': 'Canada'},
        'vancouver': {'lat': 49.2827, 'lon': -123.1207, 'country': 'Canada'},
        'mexico city': {'lat': 19.4326, 'lon': -99.1332, 'country': 'Mexico'},
        'bogota': {'lat': 4.7110, 'lon': -74.0721, 'country': 'Colombia'},
        'caracas': {'lat': 10.4806, 'lon': -66.9036, 'country': 'Venezuela'},
        'lima': {'lat': -12.0464, 'lon': -77.0428, 'country': 'Peru'},
        'brasilia': {'lat': -15.7942, 'lon': -47.8822, 'country': 'Brazil'},
        'sao paulo': {'lat': -23.5505, 'lon': -46.6333, 'country': 'Brazil'},
        'buenos aires': {'lat': -34.6037, 'lon': -58.3816, 'country': 'Argentina'},
        'havana': {'lat': 23.1136, 'lon': -82.3666, 'country': 'Cuba'},
        # Africa
        'cairo': {'lat': 30.0444, 'lon': 31.2357, 'country': 'Egypt'},
        'tripoli': {'lat': 32.8872, 'lon': 13.1913, 'country': 'Libya'},
        'tunis': {'lat': 36.8065, 'lon': 10.1815, 'country': 'Tunisia'},
        'algiers': {'lat': 36.7372, 'lon': 3.0865, 'country': 'Algeria'},
        'rabat': {'lat': 34.0209, 'lon': -6.8416, 'country': 'Morocco'},
        'khartoum': {'lat': 15.5007, 'lon': 32.5599, 'country': 'Sudan'},
        'addis ababa': {'lat': 9.0320, 'lon': 38.7469, 'country': 'Ethiopia'},
        'mogadishu': {'lat': 2.0469, 'lon': 45.3182, 'country': 'Somalia'},
        'nairobi': {'lat': -1.2921, 'lon': 36.8219, 'country': 'Kenya'},
        'lagos': {'lat': 6.5244, 'lon': 3.3792, 'country': 'Nigeria'},
        'abuja': {'lat': 9.0765, 'lon': 7.3986, 'country': 'Nigeria'},
        'kinshasa': {'lat': -4.4419, 'lon': 15.2663, 'country': 'DRC'},
        'johannesburg': {'lat': -26.2041, 'lon': 28.0473, 'country': 'South Africa'},
        'pretoria': {'lat': -25.7461, 'lon': 28.1881, 'country': 'South Africa'},
        'harare': {'lat': -17.8252, 'lon': 31.0335, 'country': 'Zimbabwe'},
        'bamako': {'lat': 12.6392, 'lon': -8.0029, 'country': 'Mali'},
        'niamey': {'lat': 13.5137, 'lon': 2.1098, 'country': 'Niger'},
        'ndjamena': {'lat': 12.1348, 'lon': 15.0557, 'country': 'Chad'},
        # Africa - expanded
        'accra': {'lat': 5.6037, 'lon': -0.1870, 'country': 'Ghana'},
        'dakar': {'lat': 14.7167, 'lon': -17.4677, 'country': 'Senegal'},
        'abidjan': {'lat': 5.3599, 'lon': -4.0083, 'country': 'Ivory Coast'},
        'yamoussoukro': {'lat': 6.8276, 'lon': -5.2893, 'country': 'Ivory Coast'},
        'ouagadougou': {'lat': 12.3569, 'lon': -1.5352, 'country': 'Burkina Faso'},
        'conakry': {'lat': 9.6412, 'lon': -13.5784, 'country': 'Guinea'},
        'freetown': {'lat': 8.4657, 'lon': -13.2317, 'country': 'Sierra Leone'},
        'monrovia': {'lat': 6.3106, 'lon': -10.8047, 'country': 'Liberia'},
        'banjul': {'lat': 13.4549, 'lon': -16.5790, 'country': 'Gambia'},
        'bissau': {'lat': 11.8636, 'lon': -15.5977, 'country': 'Guinea-Bissau'},
        'nouakchott': {'lat': 18.0735, 'lon': -15.9582, 'country': 'Mauritania'},
        'lome': {'lat': 6.1375, 'lon': 1.2123, 'country': 'Togo'},
        'cotonou': {'lat': 6.3654, 'lon': 2.4183, 'country': 'Benin'},
        'porto-novo': {'lat': 6.4969, 'lon': 2.6289, 'country': 'Benin'},
        'malabo': {'lat': 3.7500, 'lon': 8.7833, 'country': 'Equatorial Guinea'},
        'libreville': {'lat': 0.3902, 'lon': 9.4544, 'country': 'Gabon'},
        'brazzaville': {'lat': -4.2634, 'lon': 15.2429, 'country': 'Congo'},
        'bangui': {'lat': 4.3612, 'lon': 18.5550, 'country': 'Central African Republic'},
        'yaounde': {'lat': 3.8480, 'lon': 11.5021, 'country': 'Cameroon'},
        'douala': {'lat': 4.0511, 'lon': 9.7679, 'country': 'Cameroon'},
        'luanda': {'lat': -8.8368, 'lon': 13.2343, 'country': 'Angola'},
        'lusaka': {'lat': -15.3875, 'lon': 28.3228, 'country': 'Zambia'},
        'lilongwe': {'lat': -13.9626, 'lon': 33.7741, 'country': 'Malawi'},
        'maputo': {'lat': -25.9692, 'lon': 32.5732, 'country': 'Mozambique'},
        'antananarivo': {'lat': -18.9137, 'lon': 47.5361, 'country': 'Madagascar'},
        'dar es salaam': {'lat': -6.7924, 'lon': 39.2083, 'country': 'Tanzania'},
        'kampala': {'lat': 0.3163, 'lon': 32.5822, 'country': 'Uganda'},
        'kigali': {'lat': -1.9441, 'lon': 30.0619, 'country': 'Rwanda'},
        'bujumbura': {'lat': -3.3614, 'lon': 29.3599, 'country': 'Burundi'},
        'djibouti': {'lat': 11.5720, 'lon': 43.1456, 'country': 'Djibouti'},
        'asmara': {'lat': 15.3229, 'lon': 38.9251, 'country': 'Eritrea'},
        'juba': {'lat': 4.8594, 'lon': 31.5713, 'country': 'South Sudan'},
        'gaborone': {'lat': -24.6282, 'lon': 25.9231, 'country': 'Botswana'},
        'windhoek': {'lat': -22.5597, 'lon': 17.0832, 'country': 'Namibia'},
        'maseru': {'lat': -29.3142, 'lon': 27.4833, 'country': 'Lesotho'},
        'mbabane': {'lat': -26.3054, 'lon': 31.1367, 'country': 'Eswatini'},
        'moroni': {'lat': -11.7022, 'lon': 43.2551, 'country': 'Comoros'},
        'victoria': {'lat': -4.6191, 'lon': 55.4513, 'country': 'Seychelles'},
        # Latin America - expanded
        'santiago': {'lat': -33.4489, 'lon': -70.6693, 'country': 'Chile'},
        'quito': {'lat': -0.1807, 'lon': -78.4678, 'country': 'Ecuador'},
        'guayaquil': {'lat': -2.1710, 'lon': -79.9224, 'country': 'Ecuador'},
        'la paz': {'lat': -16.5000, 'lon': -68.1500, 'country': 'Bolivia'},
        'asuncion': {'lat': -25.2867, 'lon': -57.6470, 'country': 'Paraguay'},
        'montevideo': {'lat': -34.9011, 'lon': -56.1645, 'country': 'Uruguay'},
        'rio de janeiro': {'lat': -22.9068, 'lon': -43.1729, 'country': 'Brazil'},
        'manaus': {'lat': -3.1190, 'lon': -60.0217, 'country': 'Brazil'},
        'recife': {'lat': -8.0476, 'lon': -34.8770, 'country': 'Brazil'},
        'panama city': {'lat': 8.9936, 'lon': -79.5197, 'country': 'Panama'},
        'san jose': {'lat': 9.9281, 'lon': -84.0907, 'country': 'Costa Rica'},
        'managua': {'lat': 12.1364, 'lon': -86.2514, 'country': 'Nicaragua'},
        'tegucigalpa': {'lat': 14.0723, 'lon': -87.2020, 'country': 'Honduras'},
        'san salvador': {'lat': 13.6929, 'lon': -89.2182, 'country': 'El Salvador'},
        'guatemala city': {'lat': 14.6349, 'lon': -90.5069, 'country': 'Guatemala'},
        'port-au-prince': {'lat': 18.5944, 'lon': -72.3074, 'country': 'Haiti'},
        'santo domingo': {'lat': 18.4861, 'lon': -69.9312, 'country': 'Dominican Republic'},
        'kingston': {'lat': 17.9970, 'lon': -76.7936, 'country': 'Jamaica'},
        'georgetown': {'lat': 6.8013, 'lon': -58.1553, 'country': 'Guyana'},
        'paramaribo': {'lat': 5.8664, 'lon': -55.1668, 'country': 'Suriname'},
        'medellin': {'lat': 6.2442, 'lon': -75.5812, 'country': 'Colombia'},
        'cali': {'lat': 3.4516, 'lon': -76.5320, 'country': 'Colombia'},
        'maracaibo': {'lat': 10.6424, 'lon': -71.6125, 'country': 'Venezuela'},
        # Central Asia
        'almaty': {'lat': 43.2220, 'lon': 76.8512, 'country': 'Kazakhstan'},
        'nur-sultan': {'lat': 51.1801, 'lon': 71.4460, 'country': 'Kazakhstan'},
        'tashkent': {'lat': 41.2995, 'lon': 69.2401, 'country': 'Uzbekistan'},
        'samarkand': {'lat': 39.6542, 'lon': 66.9758, 'country': 'Uzbekistan'},
        'bishkek': {'lat': 42.8746, 'lon': 74.5698, 'country': 'Kyrgyzstan'},
        'dushanbe': {'lat': 38.5598, 'lon': 68.7870, 'country': 'Tajikistan'},
        'ashgabat': {'lat': 37.9601, 'lon': 58.3261, 'country': 'Turkmenistan'},
        'yerevan': {'lat': 40.1872, 'lon': 44.5152, 'country': 'Armenia'},
        # South Asia - expanded
        'lahore': {'lat': 31.5204, 'lon': 74.3587, 'country': 'Pakistan'},
        'peshawar': {'lat': 34.0151, 'lon': 71.5249, 'country': 'Pakistan'},
        'quetta': {'lat': 30.1798, 'lon': 66.9750, 'country': 'Pakistan'},
        'bangalore': {'lat': 12.9716, 'lon': 77.5946, 'country': 'India'},
        'chennai': {'lat': 13.0827, 'lon': 80.2707, 'country': 'India'},
        'hyderabad': {'lat': 17.3850, 'lon': 78.4867, 'country': 'India'},
        'kolkata': {'lat': 22.5726, 'lon': 88.3639, 'country': 'India'},
        'ahmedabad': {'lat': 23.0225, 'lon': 72.5714, 'country': 'India'},
        'chittagong': {'lat': 22.3569, 'lon': 91.7832, 'country': 'Bangladesh'},
        'thimphu': {'lat': 27.4728, 'lon': 89.6393, 'country': 'Bhutan'},
        # Southeast Asia - expanded
        'phnom penh': {'lat': 11.5564, 'lon': 104.9282, 'country': 'Cambodia'},
        'vientiane': {'lat': 17.9757, 'lon': 102.6331, 'country': 'Laos'},
        'nay pyi taw': {'lat': 19.7633, 'lon': 96.0785, 'country': 'Myanmar'},
        'bandar seri begawan': {'lat': 4.9031, 'lon': 114.9398, 'country': 'Brunei'},
        'dili': {'lat': -8.5569, 'lon': 125.5603, 'country': 'Timor-Leste'},
        'surabaya': {'lat': -7.2575, 'lon': 112.7521, 'country': 'Indonesia'},
        'cebu': {'lat': 10.3157, 'lon': 123.8854, 'country': 'Philippines'},
        'davao': {'lat': 7.1907, 'lon': 125.4553, 'country': 'Philippines'},
        # Pacific
        'canberra': {'lat': -35.2809, 'lon': 149.1300, 'country': 'Australia'},
        'sydney': {'lat': -33.8688, 'lon': 151.2093, 'country': 'Australia'},
        'melbourne': {'lat': -37.8136, 'lon': 144.9631, 'country': 'Australia'},
        'perth': {'lat': -31.9505, 'lon': 115.8605, 'country': 'Australia'},
        'wellington': {'lat': -41.2865, 'lon': 174.7762, 'country': 'New Zealand'},
        'auckland': {'lat': -36.8485, 'lon': 174.7633, 'country': 'New Zealand'},
        'port moresby': {'lat': -9.4438, 'lon': 147.1803, 'country': 'Papua New Guinea'},
        'suva': {'lat': -18.1416, 'lon': 178.4419, 'country': 'Fiji'},
        'honiara': {'lat': -9.4319, 'lon': 160.0624, 'country': 'Solomon Islands'},
        'nuku alofa': {'lat': -21.1394, 'lon': -175.2049, 'country': 'Tonga'},
        'apia': {'lat': -13.8506, 'lon': -171.7513, 'country': 'Samoa'},
        # Europe - expanded
        'vienna': {'lat': 48.2082, 'lon': 16.3738, 'country': 'Austria'},
        'zurich': {'lat': 47.3769, 'lon': 8.5417, 'country': 'Switzerland'},
        'amsterdam': {'lat': 52.3676, 'lon': 4.9041, 'country': 'Netherlands'},
        'oslo': {'lat': 59.9139, 'lon': 10.7522, 'country': 'Norway'},
        'copenhagen': {'lat': 55.6761, 'lon': 12.5683, 'country': 'Denmark'},
        'lisbon': {'lat': 38.7223, 'lon': -9.1393, 'country': 'Portugal'},
        'athens': {'lat': 37.9838, 'lon': 23.7275, 'country': 'Greece'},
        'budapest': {'lat': 47.4979, 'lon': 19.0402, 'country': 'Hungary'},
        'prague': {'lat': 50.0755, 'lon': 14.4378, 'country': 'Czech Republic'},
        'sofia': {'lat': 42.6977, 'lon': 23.3219, 'country': 'Bulgaria'},
        'zagreb': {'lat': 45.8150, 'lon': 15.9819, 'country': 'Croatia'},
        'sarajevo': {'lat': 43.8563, 'lon': 18.4131, 'country': 'Bosnia'},
        'skopje': {'lat': 41.9981, 'lon': 21.4254, 'country': 'North Macedonia'},
        'tirana': {'lat': 41.3275, 'lon': 19.8187, 'country': 'Albania'},
        'chisinau': {'lat': 47.0105, 'lon': 28.8638, 'country': 'Moldova'},
        'riga': {'lat': 56.9460, 'lon': 24.1059, 'country': 'Latvia'},
        'vilnius': {'lat': 54.6872, 'lon': 25.2797, 'country': 'Lithuania'},
        'tallinn': {'lat': 59.4370, 'lon': 24.7536, 'country': 'Estonia'},
        'reykjavik': {'lat': 64.1466, 'lon': -21.9426, 'country': 'Iceland'},
        'valletta': {'lat': 35.8997, 'lon': 14.5147, 'country': 'Malta'},
        'nicosia': {'lat': 35.1856, 'lon': 33.3823, 'country': 'Cyprus'},
        # East Asia - expanded
        'chengdu': {'lat': 30.5728, 'lon': 104.0668, 'country': 'China'},
        'wuhan': {'lat': 30.5928, 'lon': 114.3055, 'country': 'China'},
        'guangzhou': {'lat': 23.1291, 'lon': 113.2644, 'country': 'China'},
        'shenzhen': {'lat': 22.5431, 'lon': 114.0579, 'country': 'China'},
        'urumqi': {'lat': 43.8256, 'lon': 87.6168, 'country': 'China'},
        'lhasa': {'lat': 29.6500, 'lon': 91.1000, 'country': 'China'},
        'ulaanbaatar': {'lat': 47.8864, 'lon': 106.9057, 'country': 'Mongolia'},
    }

    # Keywords for crisis type detection. Dict order matters — first match
    # wins (see _extract_crisis_from_article) — so leadership_change and
    # civil_unrest must come before conflict/military, since a coup or
    # protest story often also contains generic "armed"/"military" words.
    CRISIS_KEYWORDS = {
        'leadership_change': ['coup', 'ousted', 'overthrown', 'seized power', 'junta',
                               'assassinated', 'resigns as president', 'unconstitutional',
                               'succession crisis'],
        'civil_unrest': ['protest', 'unrest', 'riot', 'demonstrators', 'uprising',
                          'crackdown', 'mass arrests', 'general strike'],
        'conflict': ['war', 'combat', 'fighting', 'battle', 'attack', 'strike', 'bomb', 'military', 'armed', 'clash'],
        'military': ['military', 'deployment', 'exercise', 'buildup', 'troops', 'forces', 'defense'],
        'diplomatic': ['diplomatic', 'crisis', 'tensions', 'talks', 'negotiations', 'standoff',
                        'peace deal', 'peace agreement', 'ceasefire signed', 'ceasefire agreed'],
        'alliance': ['alliance', 'joins nato', 'treaty signed', 'accession',
                      'mutual defense pact', 'normalizes relations'],
        'economic': ['economic', 'embargo', 'sanction', 'trade', 'crisis', 'collapse'],
        'resource': ['resource', 'oil', 'gas', 'commodity', 'supply', 'shortage'],
        'technology': ['technology', 'cyber', 'ai', 'chip', 'semiconductor'],
        'proxy': ['proxy', 'indirect', 'support', 'militia'],
    }

    # Wire-service articles conventionally open with a dateline naming the
    # REPORTING BUREAU's city, not necessarily the story's subject — e.g.
    # "LIMA, Sept 20 (Reuters) - Officials warned that conflict is
    # worsening across the Sahel..." is a story about Africa, datelined
    # from Lima. Matching that blindly mis-geocoded several real articles
    # to the dateline city instead of the story's actual location, so it's
    # stripped from the description before city-matching runs.
    DATELINE_RE = re.compile(r'^\s*[A-Z][A-Za-z0-9.,\s]{1,40}\([^)]{1,30}\)\s*[-–—]\s*')

    # Lazily-built, cached (pattern, city_name) list for LOCATION_MAP —
    # compiled once (not per-article) since this runs against every
    # article in every sync. See _find_earliest_city for why word-boundary
    # regex + earliest-position matching replaced a plain substring check.
    _location_patterns = None

    @staticmethod
    def _get_location_patterns():
        if NewsBasedCrisisDetector._location_patterns is None:
            NewsBasedCrisisDetector._location_patterns = [
                (re.compile(r'\b' + re.escape(city) + r'\b'), city)
                for city in NewsBasedCrisisDetector.LOCATION_MAP
            ]
        return NewsBasedCrisisDetector._location_patterns

    @staticmethod
    def _find_earliest_city(text):
        """
        Return the LOCATION_MAP city name that appears earliest in `text`,
        or None. Word-boundary matched (not a plain substring check) so a
        short city name can't match inside an unrelated longer word, and
        picks whichever mentioned city occurs FIRST in the text rather than
        whichever happens to be defined first in LOCATION_MAP — dict-order
        matching was arbitrary and let an unrelated city anywhere in the
        article outrank the article's actual subject.
        """
        best = None  # (position, city_name)
        for pattern, city_name in NewsBasedCrisisDetector._get_location_patterns():
            match = pattern.search(text)
            if match and (best is None or match.start() < best[0]):
                best = (match.start(), city_name)
        return best[1] if best else None

    # Lazily-built, cached (pattern, actor_id) list from the real Actor
    # roster — rebuilt once per process, same reasoning as
    # _get_location_patterns. The roster is curated seed data (init_actors)
    # that doesn't change while a process is running.
    _actor_name_patterns = None

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
            finally:
                session.close()
        return NewsBasedCrisisDetector._actor_name_patterns

    @staticmethod
    def _find_stakeholders(text):
        """
        Real actor ids whose full name (from the curated Actor roster)
        appears in `text`, word-boundary matched like _find_earliest_city.
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

            # Topic-relevance check runs FIRST, before any geocoding — an
            # off-topic article shouldn't spend an LLM call or a Nominatim
            # request just to be discarded a moment later anyway. REQUIRE at
            # least one crisis-relevant keyword to actually be present; this
            # used to default to 'conflict' when nothing matched, which meant
            # the only real gate on "is this a crisis" was having a
            # recognized city name — any article mentioning a mapped city (a
            # filmmaker survey, a ballet review) got accepted regardless of
            # topic.
            crisis_type = None
            for ctype, keywords in NewsBasedCrisisDetector.CRISIS_KEYWORDS.items():
                if any(kw in text_lower for kw in keywords):
                    crisis_type = ctype
                    break

            if crisis_type is None:
                return None

            # Geocoding: try a real, incident-level location first — AI
            # extraction of the specific place genuinely tied to this
            # event (a landmark, a capital, an ad-hoc reported location),
            # geocoded via Nominatim — since that generalizes to anything
            # (the UN, the White House, a neighborhood a missile was heard
            # over) the curated LOCATION_MAP below was never going to cover.
            # Falls back to the curated city-name match whenever the AI
            # path finds nothing (including when ANTHROPIC_API_KEY isn't
            # configured) or Nominatim has no result — never worse than the
            # old behavior, meaningfully better whenever a key is set.
            location = None
            lat, lon = None, None
            country = None
            location_confidence = 82

            extracted_place = _extract_incident_location(title + '. ' + description_for_location)
            if extracted_place:
                geocoded = NominatimGeocoder.geocode(extracted_place)
                # Crisis.country is a required field — only accept this
                # result if Nominatim actually returned one, otherwise fall
                # through to the city-match path below rather than crash
                # (or silently drop the crisis) on a null country.
                if geocoded and geocoded.get('country'):
                    location = extracted_place
                    lat = geocoded['lat']
                    lon = geocoded['lon']
                    country = geocoded['country']
                    # Higher confidence than a bare city match — this is a
                    # specific, AI-identified real-world location, not just
                    # "some city was named somewhere in the text."
                    location_confidence = 90

            if not location:
                # Search the TITLE first: a city named in the headline is
                # almost always the article's actual subject, whereas the
                # DESCRIPTION often opens with a wire-service dateline
                # naming the reporting bureau's city, unrelated to the
                # story (e.g. a "LIMA (Reuters) -" prefix on a story about
                # Africa) — matching that blindly used to mis-geocode
                # articles to the wrong country. Only fall back to the full
                # title+description text if the title alone names no known
                # city.
                matched_city = (
                    NewsBasedCrisisDetector._find_earliest_city(title.lower())
                    or NewsBasedCrisisDetector._find_earliest_city(text_lower)
                )
                if matched_city:
                    coords = NewsBasedCrisisDetector.LOCATION_MAP[matched_city]
                    location = matched_city.title()
                    lat = coords['lat']
                    lon = coords['lon']
                    country = coords['country']
                    location_confidence = 82

            # Skip article if no specific location found — we only plot verified locations
            if not location:
                return None

            # Calculate severity based on keywords
            severity_keywords = {
                'death': 20, 'killed': 20, 'wounded': 15,
                'war': 80, 'attack': 60, 'bomb': 70,
                'nuclear': 95, 'missile': 75,
                'military': 50, 'conflict': 70,
                'crisis': 60, 'tension': 40,
            }

            severity = 50  # Base severity
            for keyword, weight in severity_keywords.items():
                if keyword in text_lower:
                    severity = max(severity, weight)

            # Create unique ID
            crisis_id = f"news_{source.lower().replace(' ', '_')}_{published[:10]}"

            # Real actor ids mentioned by name in the article — [] when
            # nothing matches, never a guessed default (see _find_stakeholders).
            stakeholders = NewsBasedCrisisDetector._find_stakeholders(title + ' ' + description)

            return {
                'id': crisis_id,
                'type': crisis_type,
                'title': title[:200],
                'country': country,   # actual country (e.g. "Iran")
                'latitude': lat,      # exact city lat
                'longitude': lon,     # exact city lon
                'severity': min(100, severity),
                'confidence': 75,
                'location_confidence': location_confidence,  # 90 for AI+Nominatim, 82 for curated city match
                'date_start': datetime.fromisoformat(published.replace('Z', '+00:00')) if published else datetime.utcnow(),
                'analysis': description[:500] if description else title,
                'impact': f"Reported by {source}",
                'source': 'NewsAPI',
                'source_id': url,
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


class DataAggregator:
    """Aggregate data from multiple sources into Crisis records"""

    @staticmethod
    def sync_all_sources():
        """Fetch and sync all data sources"""
        logger.info("Starting data sync...")

        session = Session()

        try:
            # Try ACLED first (if available)
            acled_crises = ACLEDConnector.fetch_recent_events(days=30)
            for crisis_data in acled_crises:
                DataAggregator._upsert_crisis(session, crisis_data)

            # Also fetch real crises from news articles
            news_crises = NewsBasedCrisisDetector.extract_crises_from_news(days=7)
            for crisis_data in news_crises:
                DataAggregator._upsert_crisis(session, crisis_data)

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

            session.commit()
            logger.info("Data sync completed successfully")

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
    def _upsert_crisis(session, crisis_data):
        """Insert or update crisis"""
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
