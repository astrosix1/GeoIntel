"""
Data source connectors for real-world geopolitical data
"""
from datetime import datetime

from models import Crisis, News, Actor, Relationship, EconomicData, CrisisSnapshot, Session

from ._shared import logger

# Re-export everything from the submodules below so existing call sites
# elsewhere in the codebase (`from data_sources import GDELTConnector`,
# `import data_sources as ds; ds.GDELTConnector`, etc.) keep working
# unchanged after the split into this package.
from .constants import CRISIS_TYPES, ACTOR_WB_COUNTRY_OVERRIDES
from .utils import (
    _TITLE_TAG_RE, _META_DESC_RE, _DATE_ONLY_TITLE_RE, _TITLE_SOURCE_SUFFIX_RE,
    _clean_article_title, fetch_real_page_metadata,
)
from .geocoding import NOMINATIM_BASE, _geocode_ai_client, NominatimGeocoder, _extract_incident_location

# Fields a location refinement owns; sync leaves them alone on a refined row.
_REFINED_LOCATION_FIELDS = ('latitude', 'longitude', 'country', 'location_confidence')
from .gdelt import cameo_kind  # noqa: F401  (re-exported for callers and tests)
from .acled import ACLED_OAUTH_URL, ACLED_BASE, ACLED_TYPE_MAP, _acled_token_cache, ACLEDConnector
from .newsapi import NEWSAPI_BASE, NewsAPIConnector, NewsBasedCrisisDetector
from .worldbank import WORLDBANK_BASE, WorldBankConnector
from .rest_countries import REST_COUNTRIES_BASE, RestCountriesConnector
from .oec import OEC_BASE, OECConnector
from .gdacs import GDACS_EVENTS_URL, GDACSConnector
from .gdelt import (
    GDELT_LASTUPDATE_URL, GDELT_EVENT_URL_TEMPLATE, GDELT_TYPE_MAP, GDELT_EVENT_VERB,
    GDELT_OFFTOPIC_URL_SIGNALS, GDELT_POSSIBLY_OFFTOPIC_SIGNALS,
    GDELT_NONSTATE_ACTOR_TYPES, GDELT_GENERIC_ACTOR_NAMES, GDELT_DEMONYM_TO_COUNTRY,
    GDELT_BLANK_ACTOR_VIOLENT_ROOTS, GDELT_GENERIC_FALLBACK_TITLE_PREFIX, GDELTConnector,
)
from .seed_data import init_actors, init_relationships, init_scheduled_events, _SCHEDULED_EVENTS_PATH


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

            # GDELT — free, real, no-key alternative/addition to ACLED
            # (see GDELTConnector). Caught locally rather than letting a
            # GDELT-side failure bubble to this function's outer except,
            # which would roll back the ACLED/news/economic work already
            # staged in this same session — a GDELT hiccup must only cost
            # GDELT's own rows, never the rest of the sync.
            try:
                gdelt_crises = GDELTConnector.fetch_recent_events()
                for crisis_data in gdelt_crises:
                    DataAggregator._upsert_crisis(session, crisis_data)
            except Exception as e:
                logger.error(f"GDELT sync error: {e}")

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
                # A pin refined from its article (location_refined_at set) keeps
                # that position; the feed's coarse coordinates must not undo it.
                keep_location = existing.location_refined_at is not None
                # A scored story keeps its severity; the feed's raw value must not undo it.
                keep_severity = existing.severity_basis is not None
                for key, value in crisis_data.items():
                    if keep_location and key in _REFINED_LOCATION_FIELDS:
                        continue
                    if keep_severity and key == 'severity':
                        continue
                    setattr(existing, key, value)
            else:
                crisis = Crisis(**crisis_data)
                from services.severity import rescore
                rescore(crisis)     # provisional, headline-only until the article is read
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




if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    init_actors()
    DataAggregator.sync_all_sources()
