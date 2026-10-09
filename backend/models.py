"""
Database models for GeoIntel platform
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime
import json
import os

_DEFAULT_DB = 'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geointel.db')
DATABASE_URL = os.getenv('DATABASE_URL', _DEFAULT_DB)

# Configure engine with connection pooling
if DATABASE_URL.startswith('sqlite'):
    # SQLite doesn't benefit from connection pooling, disable it
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
else:
    # PostgreSQL with proper pooling
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_pre_ping=True
    )

Session = sessionmaker(bind=engine)
Base = declarative_base()


class Crisis(Base):
    """Represents a geopolitical crisis or conflict"""
    __tablename__ = 'crises'
    __table_args__ = (
        # Covers the list endpoint's filter (is_active, scope) + date window/sort.
        Index('ix_crises_active_scope_date', 'is_active', 'scope', 'date_start'),
    )

    id = Column(String(50), primary_key=True)
    type = Column(String(50), nullable=False)  # conflict, military, diplomatic, economic, resource, alliance, proxy, technology, cyber, infrastructure, migration, trade_war, bioweapon, orbital
    title = Column(String(200), nullable=False)
    country = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    severity = Column(Integer, default=50)  # 0-100
    confidence = Column(Integer, default=70)  # 0-100 (source reliability)
    location_confidence = Column(Integer, default=70)  # 0-100 (how certain is the location?)
    # Set once a definitive attempt to refine the pin from the source article
    # has finished, so it is never repeated. location_refined_name is the
    # specific place found; NULL with refined_at set means "tried, none usable".
    location_refined_at = Column(DateTime, nullable=True)
    location_refined_name = Column(String(200), nullable=True)
    # 'statement' (talks, criticism, threats: no physical site, so its pin is only
    # approximate by nature) | 'physical' (it happened somewhere) | NULL (unknown).
    event_kind = Column(String(12), nullable=True)
    # Stage 2 of the story pipeline (services/story_facts.py): a short body excerpt of the
    # source article, the facts extracted from it (JSON text), and when that finished.
    article_excerpt = Column(Text, nullable=True)
    facts = Column(Text, nullable=True)
    facts_extracted_at = Column(DateTime, nullable=True)
    # Strict severity (services/severity.py): level 1-5 and the JSON reasons behind it.
    severity_level = Column(Integer, nullable=True)
    severity_basis = Column(Text, nullable=True)
    # Story merging (services/stories.py): a duplicate points at the story's primary
    # event and is inactive; `source_count` is the number of distinct outlets behind a story.
    merged_into = Column(String(50), nullable=True, index=True)
    source_count = Column(Integer, nullable=False, default=1, server_default='1')
    # Other countries the same article was tagged with when its duplicates were merged (JSON list).
    also_tagged = Column(Text, nullable=True)
    # Why an event was hidden without being a duplicate: 'template', 'domain' or 'site' (a junk title).
    hidden_reason = Column(String(20), nullable=True)
    # Why the event is Global or Local (services/scope.py): JSON {rule, global: [terms], local: [terms]}. NULL = not yet judged by topic.
    scope_basis = Column(Text, nullable=True)

    date_start = Column(DateTime, default=datetime.utcnow)
    date_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Future-dated events (elections, referendums) are known in advance,
    # unlike every other crisis type which is detected reactively from news
    # after the fact. date_start stays the ingestion time (so the year-
    # slider's exact-calendar-year filtering — see filterByDateRange() in
    # app.js — still shows the pin today); date_scheduled is the real future
    # date, used only for display. status distinguishes a scheduled event
    # that hasn't happened yet from an active/resolved one.
    date_scheduled = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default='active', index=True)  # active | upcoming | resolved

    analysis = Column(Text)
    impact = Column(Text)

    stakeholders = Column(String(500))  # JSON-encoded list of actor codes

    # Multi-domain impact scores
    military_score = Column(Integer, default=0)
    economic_score = Column(Integer, default=0)
    political_score = Column(Integer, default=0)
    environment_score = Column(Integer, default=0)
    technology_score = Column(Integer, default=0)
    information_score = Column(Integer, default=0)

    # Source tracking
    source = Column(String(100))  # ACLED, NEWS_API, MANUAL, etc
    source_id = Column(String(100))  # ID in external system
    source_url = Column(String(500))  # Real link to the original source article/record, when known

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # Human-verified

    # 'global' | 'local' — a real classification, not geography: 'local'
    # means small-scale, non-geopolitical content (routine city/town crime,
    # accidents, human-interest stories) that GDELT's CAMEO parser
    # mis-tags as conflict. Only GDELTConnector._parse_row's own
    # confirmed noise signals (self-referential/demonym-self-referential
    # actor pairs, generic-actor names, blank-actor-under-violent-root)
    # set this to 'local'; every other row (all of ACLED/NewsAPI, and
    # GDELT rows that pass every filter cleanly) defaults to 'global' —
    # the safe backward-compatible default for existing rows.
    scope = Column(String(10), nullable=False, default='global')

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'country': self.country,
            'lat': self.latitude,
            'lon': self.longitude,
            'severity': self.severity,
            'confidence': self.confidence,
            'location_confidence': self.location_confidence,
            'location_refined_name': self.location_refined_name,
            'severity_level': self.severity_level,
            'severity_basis': json.loads(self.severity_basis) if self.severity_basis else None,
            'event_kind': self.event_kind,
            'source_count': self.source_count or 1,
            'merged_into': self.merged_into,
            'also_tagged': json.loads(self.also_tagged) if self.also_tagged else [],
            'location_refined_at': self.location_refined_at.isoformat() if self.location_refined_at else None,
            'date': self.date_start.isoformat() if self.date_start else None,
            'date_scheduled': self.date_scheduled.isoformat() if self.date_scheduled else None,
            'status': self.status,
            'analysis': self.analysis,
            'impact': self.impact,
            'stakeholders': self.stakeholders.split(',') if self.stakeholders else [],
            'domains': {
                'military': self.military_score,
                'economic': self.economic_score,
                'political': self.political_score,
                'environment': self.environment_score,
                'technology': self.technology_score,
                'information': self.information_score,
            },
            'source': self.source,
            'source_url': self.source_url,
            'is_verified': self.is_verified,
            'scope': self.scope or 'global',
            'scope_basis': json.loads(self.scope_basis) if self.scope_basis else None,
        }


class CrisisSnapshot(Base):
    """A point-in-time severity reading for a crisis, recorded on every
    scheduled sync (see DataAggregator.snapshot_severity_history). This is
    the real time-series analyze_escalation() needs — Crisis.severity only
    ever stores the current value, with no history of its own."""
    __tablename__ = 'crisis_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    crisis_id = Column(String(50), nullable=False, index=True)
    severity = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index('ix_crisis_snapshots_crisis_recorded', 'crisis_id', 'recorded_at'),
    )


class Forecast(Base):
    """Probabilistic forecasts for crisis outcomes"""
    __tablename__ = 'forecasts'

    id = Column(String(50), primary_key=True)
    crisis_id = Column(String(50), nullable=False)

    question = Column(String(300), nullable=False)

    # Probability buckets (0-100)
    prob_unlikely = Column(Integer, default=50)  # Low probability
    prob_possible = Column(Integer, default=30)  # Medium
    prob_likely = Column(Integer, default=20)   # High

    confidence = Column(Integer, default=60)  # 0-100 confidence in forecast

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    method = Column(String(100))  # Bayesian, Expert, Historical, ML
    notes = Column(Text)

    def to_dict(self):
        return {
            'q': self.question,
            'low': self.prob_unlikely,
            'mid': self.prob_possible,
            'high': self.prob_likely,
            'confidence': self.confidence,
            'method': self.method,
        }


class Actor(Base):
    """State and non-state actors in geopolitical system"""
    __tablename__ = 'actors'

    id = Column(String(10), primary_key=True)  # US, CN, RU, etc
    name = Column(String(100), nullable=False)
    category = Column(String(50))  # STATE, NGO, MILITIA, CORPORATION

    # Real world-region grouping (North America, Europe, East Asia, South
    # Asia, Southeast Asia, Middle East, North Africa, Sub-Saharan Africa,
    # Latin America, Eastern Europe / Eurasia), set per-actor in
    # init_actors(). Used by analyze_cascade()'s affected_regions — this
    # used to always be an empty list because no such column existed at all.
    region = Column(String(50))

    latitude = Column(Float)  # Capital/HQ location
    longitude = Column(Float)

    color = Column(String(7))  # Hex color for visualization

    # No `default=` on any of these: a missing value should read as
    # "not rated" (None), never a silently fabricated number. economic_power
    # is derived from real WorldBank GDP data by
    # DataAggregator.sync_actor_power_stats (data_sources.py) whenever GDP
    # data exists for the actor's country; military_power/political_influence/
    # technological_capability have no real data source anywhere in this app
    # and stay None until one is wired in.
    military_power = Column(Integer)  # 0-100
    economic_power = Column(Integer)
    political_influence = Column(Integer)
    technological_capability = Column(Integer)

    population = Column(Integer)
    gdp = Column(Float)  # In billions USD

    is_nuclear = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'region': self.region,
            'lat': self.latitude,
            'lon': self.longitude,
            'color': self.color,
            'military': self.military_power,
            'economic': self.economic_power,
            'political': self.political_influence,
            'technology': self.technological_capability,
            'is_nuclear': self.is_nuclear,
        }


class Relationship(Base):
    """Relationships between actors"""
    __tablename__ = 'relationships'

    id = Column(String(50), primary_key=True)
    actor_a = Column(String(10), nullable=False)
    actor_b = Column(String(10), nullable=False)

    type = Column(String(50))  # alliance, conflict, tension, economic, proxy
    label = Column(String(200))

    strength = Column(Integer, default=50)  # 0-100 how strong the relationship
    stability = Column(Integer, default=50)  # 0-100 how stable over time

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'a': self.actor_a,
            'b': self.actor_b,
            'type': self.type,
            'label': self.label,
            'strength': self.strength,
            'stability': self.stability,
        }


class StoryMergeCheck(Base):
    """One AI verdict on whether two borderline events are the same story, so a pair
    is never judged twice. pair_key is the two event ids, sorted and joined with '|'."""
    __tablename__ = 'story_merge_checks'

    pair_key = Column(String(120), primary_key=True)
    same_event = Column(Boolean, nullable=False)
    checked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class News(Base):
    """Cached news articles for context"""
    __tablename__ = 'news'

    id = Column(String(100), primary_key=True)
    crisis_id = Column(String(50))

    title = Column(String(300), nullable=False)
    url = Column(String(500))
    source = Column(String(100))

    content = Column(Text)

    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    sentiment = Column(String(20))  # positive, neutral, negative
    sentiment_score = Column(Float)  # -1 to 1

    def to_dict(self):
        return {
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'sentiment': self.sentiment,
        }


class EconomicData(Base):
    """Economic indicators by country"""
    __tablename__ = 'economic_data'

    id = Column(String(50), primary_key=True)
    country_code = Column(String(3), nullable=False)

    gdp = Column(Float)  # Billions USD
    gdp_growth = Column(Float)  # % YoY

    exports = Column(Float)
    imports = Column(Float)

    inflation = Column(Float)
    unemployment = Column(Float)

    trade_balance = Column(Float)

    foreign_reserves = Column(Float)  # Billions USD
    debt_to_gdp = Column(Float)

    year = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'country': self.country_code,
            'gdp': self.gdp,
            'gdp_growth': self.gdp_growth,
            'exports': self.exports,
            'imports': self.imports,
            'inflation': self.inflation,
            'unemployment': self.unemployment,
            'trade_balance': self.trade_balance,
            'year': self.year,
        }


# Schema creation/changes are now handled by Alembic (see backend/migrations/),
# not by create_all() here. create_all() only ever creates missing tables —
# it never alters an existing one — so relying on it silently masks schema
# drift between dev and production. Run `alembic upgrade head` (from
# backend/) to create or update the database.
