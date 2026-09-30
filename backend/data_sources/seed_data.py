import os
import json

from models import Crisis, Actor, Relationship, Session
from datetime import datetime

from ._shared import logger


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


# NOTE: this module now lives at backend/data_sources/seed_data.py (moved
# from the single backend/data_sources.py during the package split) — the
# real on-disk config file is at backend/config/scheduled_events.json, one
# directory above this package, so the path is built from this package's
# parent directory, not this file's own directory.
_SCHEDULED_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'scheduled_events.json'
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
