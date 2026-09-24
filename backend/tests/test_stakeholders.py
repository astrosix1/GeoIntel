"""
Tests for stakeholder matching in data_sources.py.

Crisis.stakeholders is rendered by the frontend but previously had zero
writers anywhere in the connector pipeline. NewsBasedCrisisDetector and
ACLEDConnector now populate it by matching real actor names (from the
curated Actor roster) against the source article/event text — never a
guessed default.
"""
import pytest

from models import Actor
from data_sources import NewsBasedCrisisDetector, ACLEDConnector


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    db_session.query(Actor).delete()
    db_session.commit()
    # The actor-name pattern cache is built once per process and would
    # otherwise leak stale patterns (or an empty roster) across tests.
    NewsBasedCrisisDetector._actor_name_patterns = None
    yield
    db_session.query(Actor).delete()
    db_session.commit()
    NewsBasedCrisisDetector._actor_name_patterns = None


def seed_actors(db_session):
    db_session.add_all([
        Actor(id='US', name='United States', category='STATE', latitude=38, longitude=-97),
        Actor(id='RU', name='Russia', category='STATE', latitude=60, longitude=90),
        Actor(id='CN', name='China', category='STATE', latitude=35, longitude=105),
    ])
    db_session.commit()


def test_matches_real_actor_names_in_text(app_module, db_session):
    seed_actors(db_session)
    result = NewsBasedCrisisDetector._find_stakeholders(
        "Russia and United States trade accusations over border incident"
    )
    assert set(result) == {'RU', 'US'}


def test_no_match_returns_empty_list_not_a_guess(app_module, db_session):
    seed_actors(db_session)
    result = NewsBasedCrisisDetector._find_stakeholders(
        "Local council debates new zoning ordinance"
    )
    assert result == []


def test_matching_is_word_boundary_not_substring(app_module, db_session):
    seed_actors(db_session)
    # "Chinatown" contains "China" as a substring but must not match.
    result = NewsBasedCrisisDetector._find_stakeholders(
        "New restaurant opens in Chinatown neighborhood"
    )
    assert result == []


def test_acled_parse_event_populates_stakeholders_from_actor_fields(app_module, db_session):
    seed_actors(db_session)
    event = {
        'data_id': '12345',
        'event_type': 'Battle',
        'event_id_cnty': 'RUS1',
        'country': 'Russia',
        'latitude': '50.0',
        'longitude': '30.0',
        'fatalities': '10',
        'event_date': '2026-01-01',
        'actor1': 'Military Forces of Russia (2000-)',
        'actor2': 'Military Forces of United States (2021-)',
        'notes': 'Clash reported near the border.',
    }
    crisis = ACLEDConnector._parse_event(event)
    assert crisis is not None
    stakeholders = set(crisis['stakeholders'].split(',')) if crisis['stakeholders'] else set()
    assert stakeholders == {'RU', 'US'}


def test_acled_parse_event_empty_stakeholders_when_no_match(app_module, db_session):
    seed_actors(db_session)
    event = {
        'data_id': '99999',
        'event_type': 'Riots',
        'event_id_cnty': 'XYZ1',
        'country': 'Testland',
        'latitude': '0',
        'longitude': '0',
        'fatalities': '0',
        'event_date': '2026-01-01',
        'actor1': 'Unidentified Armed Group',
        'notes': 'No named state actors involved.',
    }
    crisis = ACLEDConnector._parse_event(event)
    assert crisis is not None
    assert crisis['stakeholders'] == ''
