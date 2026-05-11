"""
Data source connectors for real-world geopolitical data
"""
import requests
import os
from datetime import datetime, timedelta
from models import Crisis, News, Actor, Relationship, EconomicData, Session
import json
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

ACLED_BASE = "https://api.acleddata.com/api/terms"
NEWSAPI_BASE = "https://newsapi.org/v2"
WORLDBANK_BASE = "https://api.worldbank.org/v2"

# Mapping ACLED event types to our crisis types
ACLED_TYPE_MAP = {
    'Violence against civilians': 'conflict',
    'Battle': 'conflict',
    'Explosions/Remote violence': 'conflict',
    'Protests': 'migration',
    'Riots': 'conflict',
    'Strategic developments': 'military',
    'Armed clash': 'conflict',
    'Cyber attack': 'cyber',
    'Infrastructure attack': 'infrastructure',
    'Displacement': 'migration',
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
    def fetch_recent_events(days=30):
        """
        Fetch recent conflict events from ACLED
        https://acleddata.com/api
        Falls back to sample data if API unavailable
        """
        try:
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=days)

            params = {
                'country_id': [],
                'event_date': f'{start_date}|{end_date}',
                'event_type': list(ACLED_TYPE_MAP.keys()),
                'limit': 500,
            }

            # Try ACLED API
            response = requests.get(
                f"{ACLED_BASE}/year/?year={end_date.year}",
                timeout=10
            )
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

            return {
                'id': f"acled_{event.get('data_id')}",
                'type': crisis_type,
                'title': event.get('event_id_cnty', 'Unknown Event'),
                'country': event.get('country', 'Unknown'),
                'latitude': float(event.get('latitude', 0)),
                'longitude': float(event.get('longitude', 0)),
                'severity': severity,
                'confidence': 85,  # ACLED is well-documented
                'date': event.get('event_date'),
                'analysis': event.get('notes', ''),
                'impact': f"{event.get('fatalities', 0)} fatalities, {event.get('event_type')}",
                'source': 'ACLED',
                'source_id': event.get('data_id'),
                'is_verified': True,
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
                'date_start': now,
                'analysis': 'Ongoing cyber and information warfare operations.',
                'impact': 'Global infrastructure risks, geopolitical tension.',
                'source': 'Sample Data',
                'source_id': 'sample_005',
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

            return {
                'id': article.get('url', '').replace('/', '_'),
                'title': article.get('title'),
                'url': article.get('url'),
                'source': article.get('source', {}).get('name', 'Unknown'),
                'content': article.get('description', ''),
                'published_at': article.get('publishedAt'),
                'sentiment': sentiment,
                'sentiment_score': sentiment_score,
            }
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
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
    }

    # Keywords for crisis type detection
    CRISIS_KEYWORDS = {
        'conflict': ['war', 'combat', 'fighting', 'battle', 'attack', 'strike', 'bomb', 'military', 'armed', 'clash'],
        'military': ['military', 'deployment', 'exercise', 'buildup', 'troops', 'forces', 'defense'],
        'diplomatic': ['diplomatic', 'crisis', 'tensions', 'talks', 'negotiations', 'standoff'],
        'economic': ['economic', 'embargo', 'sanction', 'trade', 'crisis', 'collapse'],
        'resource': ['resource', 'oil', 'gas', 'commodity', 'supply', 'shortage'],
        'technology': ['technology', 'cyber', 'ai', 'chip', 'semiconductor'],
        'proxy': ['proxy', 'indirect', 'support', 'militia'],
    }

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
            title = article.get('title', '')
            description = article.get('description', '') or ''
            source = article.get('source', {}).get('name', 'News')
            published = article.get('publishedAt', '')
            url = article.get('url', '')

            # Combine title and description for analysis
            text_lower = (title + ' ' + description).lower()

            # Extract location — only match explicit city names in the article text
            location = None
            lat, lon = None, None
            country = None

            for city_name, coords in NewsBasedCrisisDetector.LOCATION_MAP.items():
                if city_name in text_lower:
                    location = city_name.title()
                    lat = coords['lat']
                    lon = coords['lon']
                    country = coords['country']
                    break

            # Skip article if no specific city found — we only plot verified locations
            if not location:
                return None

            # Determine crisis type
            crisis_type = 'conflict'
            for ctype, keywords in NewsBasedCrisisDetector.CRISIS_KEYWORDS.items():
                if any(kw in text_lower for kw in keywords):
                    crisis_type = ctype
                    break

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

            return {
                'id': crisis_id,
                'type': crisis_type,
                'title': title[:200],
                'country': country,   # actual country (e.g. "Iran")
                'latitude': lat,      # exact city lat
                'longitude': lon,     # exact city lon
                'severity': min(100, severity),
                'confidence': 75,
                'date_start': datetime.fromisoformat(published.replace('Z', '+00:00')) if published else datetime.utcnow(),
                'analysis': description[:500] if description else title,
                'impact': f"Reported by {source}",
                'source': 'NewsAPI',
                'source_id': url,
                'is_verified': False,
            }

        except Exception as e:
            logger.error(f"Error extracting crisis from article: {e}")
            return None


class WorldBankConnector:
    """Fetch economic data from World Bank"""

    @staticmethod
    def fetch_country_indicators(country_codes=['US', 'CN', 'RU', 'JP', 'DE', 'IN']):
        """
        Fetch economic indicators for countries
        """
        try:
            indicators = {
                'NY.GDP.MKTP.CD': 'GDP (current US$)',
                'NY.GDP.DEFL.ZS': 'GDP deflator',
                'NE.EXP.GNFS.CD': 'Exports of goods and services',
                'NE.IMP.GNFS.CD': 'Imports of goods and services',
                'FP.CPI.TOTL.ZG': 'Inflation',
                'SL.UEM.TOTL.ZS': 'Unemployment rate',
            }

            economic_data = []

            for country in country_codes:
                try:
                    # Fetch latest data for each indicator
                    for ind_code, ind_name in indicators.items():
                        response = requests.get(
                            f"{WORLDBANK_BASE}/country/{country}/indicator/{ind_code}",
                            params={'format': 'json', 'per_page': 10},
                            timeout=10
                        )
                        response.raise_for_status()

                        data = response.json()
                        if len(data) > 1:
                            for record in data[1]:
                                econ = WorldBankConnector._parse_economic_data(country, ind_code, record)
                                if econ:
                                    economic_data.append(econ)

                except Exception as e:
                    logger.warning(f"Error fetching {ind_code} for {country}: {e}")

            logger.info(f"Fetched {len(economic_data)} economic indicators")
            return economic_data

        except Exception as e:
            logger.error(f"World Bank fetch error: {e}")
            return []

    @staticmethod
    def _parse_economic_data(country, indicator, record):
        """Convert World Bank data to EconomicData object"""
        try:
            return {
                'id': f"wb_{country}_{record.get('date')}",
                'country_code': country,
                'indicator': indicator,
                'value': record.get('value'),
                'year': int(record.get('date', 0)),
            }
        except Exception as e:
            logger.error(f"Error parsing economic data: {e}")
            return None


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

            # Fetch Economic Data
            econ_data = WorldBankConnector.fetch_country_indicators()
            for econ_item in econ_data:
                DataAggregator._upsert_economic(session, econ_item)

            session.commit()
            logger.info("Data sync completed successfully")

        except Exception as e:
            session.rollback()
            logger.error(f"Data sync error: {e}")
        finally:
            session.close()

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
    """Populate core actors"""
    session = Session()

    actors_data = [
        {'id': 'US', 'name': 'United States', 'latitude': 38, 'longitude': -97, 'color': '#4488ff', 'is_nuclear': True},
        {'id': 'CN', 'name': 'China', 'latitude': 35, 'longitude': 105, 'color': '#ff4444', 'is_nuclear': True},
        {'id': 'RU', 'name': 'Russia', 'latitude': 60, 'longitude': 90, 'color': '#ff9933', 'is_nuclear': True},
        {'id': 'EU', 'name': 'European Union', 'latitude': 50, 'longitude': 10, 'color': '#88ccff', 'is_nuclear': False},
        {'id': 'IN', 'name': 'India', 'latitude': 20, 'longitude': 77, 'color': '#ff7744', 'is_nuclear': True},
        {'id': 'IR', 'name': 'Iran', 'latitude': 32, 'longitude': 53, 'color': '#cc44ff', 'is_nuclear': False},
        {'id': 'IL', 'name': 'Israel', 'latitude': 31.5, 'longitude': 35, 'color': '#4488ff', 'is_nuclear': True},
        {'id': 'NK', 'name': 'North Korea', 'latitude': 39, 'longitude': 127, 'color': '#ff4444', 'is_nuclear': True},
    ]

    for actor_data in actors_data:
        existing = session.query(Actor).filter(Actor.id == actor_data['id']).first()
        if not existing:
            actor = Actor(**actor_data)
            session.add(actor)

    session.commit()
    session.close()
    logger.info("Actors initialized")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_actors()
    DataAggregator.sync_all_sources()
