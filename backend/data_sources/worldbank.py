import requests
from collections import defaultdict

from models import Actor

from ._shared import logger
from .constants import ACTOR_WB_COUNTRY_OVERRIDES

WORLDBANK_BASE = "https://api.worldbank.org/v2"


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

    @staticmethod
    def fetch_country_meta(country_code):
        """Real country metadata (capital, region, income level, centroid)
        from WorldBank's own /country/{code} endpoint — used as the
        fallback demographics source for the countries blueprint when
        REST Countries is unavailable (it started requiring an API key;
        see data_sources/rest_countries.py). Returns None on any failure,
        never fabricated data."""
        try:
            resp = requests.get(
                f"{WORLDBANK_BASE}/country/{country_code}",
                params={'format': 'json'},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if len(data) < 2 or not data[1]:
                return None
            row = data[1][0]
            return {
                'name': row.get('name'),
                'iso3': row.get('id'),
                'iso2': row.get('iso2Code'),
                'region': (row.get('region') or {}).get('value'),
                'income_level': (row.get('incomeLevel') or {}).get('value'),
                'capital': row.get('capitalCity') or None,
                'latitude': float(row['latitude']) if row.get('latitude') else None,
                'longitude': float(row['longitude']) if row.get('longitude') else None,
            }
        except Exception as e:
            logger.warning(f"WorldBank country-meta fetch error for {country_code}: {e}")
            return None

    @staticmethod
    def fetch_latest_indicator(country_code, indicator_code, per_page=20):
        """Real latest non-null value for a single WorldBank indicator
        (walks recent years since the newest year is often not yet
        reported). Returns (value, year) or (None, None) — never a
        fabricated stand-in value."""
        try:
            resp = requests.get(
                f"{WORLDBANK_BASE}/country/{country_code}/indicator/{indicator_code}",
                params={'format': 'json', 'per_page': per_page},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if len(data) < 2 or not data[1]:
                return None, None
            for record in data[1]:
                if record.get('value') is not None:
                    return record['value'], int(record['date'])
            return None, None
        except Exception as e:
            logger.warning(f"WorldBank indicator fetch error for {country_code}/{indicator_code}: {e}")
            return None, None

