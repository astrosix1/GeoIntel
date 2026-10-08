"""
Country profile assembly — real demographics + real economic/trade facts +
an honest AI-or-static narrative for the qualitative "unique geographical/
infrastructural features" and "contribution to the rest of the world"
asks. Mirrors services/briefing.py's established AI-primary/honest-static-
fallback shape (same cache-check -> Claude-call -> fallback structure, same
`model` field convention so the frontend can reuse EventAnalysis's existing
AI-vs-static badge convention).

No number in the generated narrative is invented: the prompt is fed only
the real facts assembled below, and the static fallback (used when no
ANTHROPIC_API_KEY is configured) presents those same real facts plainly
with no generated prose at all, rather than a fabricated-sounding
paragraph.
"""
import logging
from datetime import datetime

from cache import cache_get, cache_set
from data_sources import RestCountriesConnector, OECConnector, WorldBankConnector
from services.ai_client import anthropic_client, AI_MODEL
from services import country_indicators
from services.briefing import fetch_wikipedia_image

logger = logging.getLogger(__name__)

# WorldBank indicator codes used for the demographics/trade fallback path.
_POPULATION_INDICATOR = 'SP.POP.TOTL'
_AREA_INDICATOR = 'AG.LND.TOTL.K2'
_GDP_INDICATOR = 'NY.GDP.MKTP.CD'
_EXPORTS_INDICATOR = 'NE.EXP.GNFS.ZS'  # exports as % of GDP
_IMPORTS_INDICATOR = 'NE.IMP.GNFS.ZS'  # imports as % of GDP


def _build_demographics(country_code):
    """Real demographics, preferring REST Countries; falling back to
    WorldBank's own country + indicator endpoints when REST Countries is
    unavailable (see data_sources/rest_countries.py — it now requires an
    API key in this environment). Returns (demographics_dict, source_label)."""
    rc = RestCountriesConnector.fetch_country(country_code)
    if rc:
        return {
            'name': rc.get('name'),
            'official_name': rc.get('official_name'),
            'capital': rc.get('capital'),
            'region': rc.get('region'),
            'subregion': rc.get('subregion'),
            'population': rc.get('population'),
            'area_km2': rc.get('area_km2'),
            'currencies': rc.get('currencies'),
            'languages': rc.get('languages'),
            'borders': rc.get('borders'),
            'flag_svg': rc.get('flag_svg'),
            'flag_png': rc.get('flag_png'),
        }, 'restcountries.com'

    meta = WorldBankConnector.fetch_country_meta(country_code) or {}
    population, pop_year = WorldBankConnector.fetch_latest_indicator(country_code, _POPULATION_INDICATOR)
    area, area_year = WorldBankConnector.fetch_latest_indicator(country_code, _AREA_INDICATOR)
    # The World Bank sometimes stalls on a single call; the indicator helper retries once and remembers what it fetched.
    if area is None:
        points = country_indicators.series(country_code, _AREA_INDICATOR)
        area, area_year = (points[-1][1], points[-1][0]) if points else (None, None)
    if population is None:
        points = country_indicators.series(country_code, _POPULATION_INDICATOR)
        population, pop_year = (points[-1][1], points[-1][0]) if points else (None, None)
    return {
        'name': meta.get('name'),
        'official_name': None,
        'capital': meta.get('capital'),
        'region': meta.get('region'),
        'subregion': None,
        'population': int(population) if population is not None else None,
        'population_year': pop_year,
        'area_km2': area,
        'area_year': area_year,
        'currencies': None,
        'languages': None,
        'borders': None,
        'flag_svg': None,
        'flag_png': None,
    }, 'worldbank.org (REST Countries unavailable without an API key)'


def _build_trade(country_code):
    """Real trade facts. Top-exports-by-commodity comes from OEC when it
    actually returns usable rows; otherwise honestly marked unavailable
    (never fabricated) and the macro trade-openness figures come from
    WorldBank, which is always attempted regardless of OEC's outcome."""
    top_exports = OECConnector.fetch_top_exports(country_code)

    gdp, gdp_year = WorldBankConnector.fetch_latest_indicator(country_code, _GDP_INDICATOR)
    exports_pct, exp_year = WorldBankConnector.fetch_latest_indicator(country_code, _EXPORTS_INDICATOR)
    imports_pct, imp_year = WorldBankConnector.fetch_latest_indicator(country_code, _IMPORTS_INDICATOR)

    return {
        'top_exports_by_commodity': top_exports,
        'top_exports_source': 'oec.world' if top_exports else None,
        'top_exports_unavailable_reason': (
            None if top_exports else
            "OEC's unauthenticated API tier did not return usable commodity-level "
            "export data for this country at request time; commodity-level exports "
            "require a registered OEC API key that this deployment does not have "
            "configured. Macro trade figures below are real WorldBank data instead."
        ),
        'gdp_usd_billions': round(gdp / 1e9, 1) if gdp else None,
        'gdp_year': gdp_year,
        'exports_percent_of_gdp': round(exports_pct, 1) if exports_pct is not None else None,
        'imports_percent_of_gdp': round(imports_pct, 1) if imports_pct is not None else None,
        'trade_openness_percent_of_gdp': (
            round(exports_pct + imports_pct, 1)
            if exports_pct is not None and imports_pct is not None else None
        ),
    }


def _generate_narrative(country_code, demographics, trade):
    """AI-primary/static-fallback qualitative narrative, fed only the real
    facts assembled above. Returns dict with 'geography_infrastructure',
    'world_contribution', and 'model' (mirrors briefing.py's `model` field
    convention so the frontend badge logic can be reused)."""
    facts_block = f"""
Country: {demographics.get('name') or country_code}
Capital: {demographics.get('capital') or 'unknown'}
Region: {demographics.get('region') or 'unknown'} / {demographics.get('subregion') or 'unknown'}
Population: {demographics.get('population') or 'unknown'}
Area: {demographics.get('area_km2') or 'unknown'} km2
Bordering countries: {', '.join(demographics.get('borders') or []) or 'none listed'}
GDP: {f"${trade['gdp_usd_billions']}B ({trade['gdp_year']})" if trade.get('gdp_usd_billions') else 'unknown'}
Exports as % of GDP: {trade.get('exports_percent_of_gdp', 'unknown')}
Imports as % of GDP: {trade.get('imports_percent_of_gdp', 'unknown')}
Top exported commodities (real OEC data): {trade.get('top_exports_by_commodity') or 'not available'}
"""

    if anthropic_client and anthropic_client.api_key:
        try:
            message = anthropic_client.messages.create(
                model=AI_MODEL,
                max_tokens=900,
                messages=[{
                    "role": "user",
                    "content": f"""Using ONLY the real facts below, write two short sections about this country for an intelligence-briefing sidebar:

1. "geography_infrastructure": 2-4 sentences on its geography and infrastructure relevant to trade/strategic position (coastline, borders, region) — grounded strictly in the facts given, no invented statistics.
2. "world_contribution": 2-4 sentences on its role/contribution in the world economy, grounded strictly in the GDP/trade/export facts given.

Do not state any number that is not present in the facts below. If a fact needed for a good answer is missing, say so plainly rather than guessing.

Facts:
{facts_block}

Respond as plain text with two paragraphs, the first for geography_infrastructure and the second for world_contribution, separated by a blank line. No headers, no markdown."""
                }]
            )
            text = message.content[0].text.strip()
            parts = text.split('\n\n', 1)
            geo = parts[0].strip() if parts else text
            contrib = parts[1].strip() if len(parts) > 1 else ''
            return {
                'geography_infrastructure': geo,
                'world_contribution': contrib,
                'model': AI_MODEL,
            }
        except Exception as e:
            logger.error(f"AI country-narrative error: {e}")
            # fall through to static

    logger.info("ANTHROPIC_API_KEY not set — presenting real structured facts with no generated narrative")
    return {
        'geography_infrastructure': None,
        'world_contribution': None,
        'model': 'static-facts-only',
    }


def get_country_profile(country_code):
    """
    Assemble a real CountryProfile for the given ISO alpha-2 code.
    Cached for 6 hours (these facts change slowly and every call fans out
    to 2-3 external, rate-limited APIs).
    """
    country_code = (country_code or '').upper()
    if not country_code:
        return None

    cache_key = f"country_profile:{country_code}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    demographics, demographics_source = _build_demographics(country_code)
    trade = _build_trade(country_code)
    narrative = _generate_narrative(country_code, demographics, trade)

    country_name = demographics.get('name') or country_code
    image = fetch_wikipedia_image(country_name, country_name)

    profile = {
        'country_code': country_code,
        'demographics': demographics,
        'demographics_source': demographics_source,
        'trade': trade,
        'narrative': narrative,
        'image': image,
        'generated_at': datetime.utcnow().isoformat(),
    }

    cache_set(cache_key, profile, ttl=6 * 3600)
    return profile
