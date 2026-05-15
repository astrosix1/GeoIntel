"""
Database models for GeoIntel platform
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime
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

    id = Column(String(50), primary_key=True)
    type = Column(String(50), nullable=False)  # conflict, military, diplomatic, economic, resource, alliance, proxy, technology, cyber, infrastructure, migration, trade_war, bioweapon, orbital
    title = Column(String(200), nullable=False)
    country = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    severity = Column(Integer, default=50)  # 0-100
    confidence = Column(Integer, default=70)  # 0-100 (source reliability)
    location_confidence = Column(Integer, default=70)  # 0-100 (how certain is the location?)

    date_start = Column(DateTime, default=datetime.utcnow)
    date_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # Human-verified

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
            'date': self.date_start.isoformat() if self.date_start else None,
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
            'is_verified': self.is_verified,
        }


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
        }


class Actor(Base):
    """State and non-state actors in geopolitical system"""
    __tablename__ = 'actors'

    id = Column(String(10), primary_key=True)  # US, CN, RU, etc
    name = Column(String(100), nullable=False)
    category = Column(String(50))  # STATE, NGO, MILITIA, CORPORATION

    latitude = Column(Float)  # Capital/HQ location
    longitude = Column(Float)

    color = Column(String(7))  # Hex color for visualization

    military_power = Column(Integer, default=50)  # 0-100
    economic_power = Column(Integer, default=50)
    political_influence = Column(Integer, default=50)
    technological_capability = Column(Integer, default=50)

    population = Column(Integer)
    gdp = Column(Float)  # In billions USD

    is_nuclear = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
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
        }


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
            'inflation': self.inflation,
            'year': self.year,
        }


# Create all tables
Base.metadata.create_all(engine)
