"""
REST Countries connector — real, free, no-key demographics/geography facts.

Live-verified at implementation time (2026-09-29): the historically-free
`https://restcountries.com/v3.1/...` host now returns a deprecation error
("This API version has been deprecated... migrate to v5") for both v3.1
*and* v5 paths on that domain, and the newer `https://api.restcountries.com`
host requires an API key (401 `authKeyMissing`) for every version tried.
So the plan's assumption ("confirmed free no-key API") no longer holds
live — REST Countries has moved behind auth since that research was done.

This connector still tries the free, unauthenticated endpoint first (in
case a given deployment/mirror doesn't require a key, or the project later
configures one via REST_COUNTRIES_API_KEY), and returns None on any
failure so the caller (services/country_profile.py) can fall back to the
WorldBank-derived facts instead of fabricating demographics.
"""
import os
import logging

try:
    import requests
except Exception:
    requests = None

logger = logging.getLogger(__name__)

REST_COUNTRIES_BASE = "https://restcountries.com/v3.1"
FIELDS = "name,capital,region,subregion,population,area,currencies,languages,borders,flags,latlng"


class RestCountriesConnector:
    """Fetch real demographic/geographic facts for one country by ISO alpha-2/3 code."""

    @staticmethod
    def fetch_country(code):
        """
        Returns a dict of real fields on success, or None if the live API
        is unavailable/unauthorized/errors — never fabricated data.
        """
        if not requests or not code:
            return None

        api_key = os.getenv('REST_COUNTRIES_API_KEY')
        headers = {'Accept': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        try:
            resp = requests.get(
                f"{REST_COUNTRIES_BASE}/alpha/{code}",
                params={'fields': FIELDS},
                headers=headers,
                timeout=6,
            )
            if resp.status_code != 200:
                logger.info(f"[RestCountries] {code} -> HTTP {resp.status_code}, unavailable (no fallback fabrication)")
                return None

            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else None
            if not data or not isinstance(data, dict) or data.get('success') is False:
                logger.info(f"[RestCountries] {code} -> no usable payload")
                return None

            name = data.get('name', {})
            currencies = data.get('currencies') or {}
            languages = data.get('languages') or {}

            return {
                'name': name.get('common'),
                'official_name': name.get('official'),
                'capital': (data.get('capital') or [None])[0],
                'region': data.get('region'),
                'subregion': data.get('subregion'),
                'population': data.get('population'),
                'area_km2': data.get('area'),
                'currencies': [
                    {'code': code_, 'name': v.get('name'), 'symbol': v.get('symbol')}
                    for code_, v in currencies.items()
                ],
                'languages': list(languages.values()),
                'borders': data.get('borders') or [],
                'flag_svg': (data.get('flags') or {}).get('svg'),
                'flag_png': (data.get('flags') or {}).get('png'),
                'latlng': data.get('latlng'),
                'source': 'restcountries.com',
            }
        except Exception as e:
            logger.info(f"[RestCountries] fetch failed for {code}: {e}")
            return None
