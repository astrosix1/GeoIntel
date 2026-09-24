"""
Tests for analyze_cascade() in app.py — the BFS that propagates a crisis
through the actor relationship graph. Unlike escalation/reliability, this
one reads Actor/Relationship/Crisis rows straight from the DB, so each
test seeds exactly the rows it needs and cleans up afterwards to stay
independent of test order.
"""
import pytest

from models import Actor, Relationship, Crisis


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    """Cascade traversal reads the *entire* actors/relationships table
    (`session.query(Actor).all()`), so leftover rows from another test
    could change which nodes a BFS reaches. Clear before and after."""
    db_session.query(Relationship).delete()
    db_session.query(Actor).delete()
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(Relationship).delete()
    db_session.query(Actor).delete()
    db_session.query(Crisis).delete()
    db_session.commit()


def seed_alliance_scenario(db_session, strength=80):
    db_session.add_all([
        Actor(id='TL', name='Testland', category='STATE', latitude=0, longitude=0),
        Actor(id='AL', name='Ally Nation', category='STATE', latitude=1, longitude=1),
        Relationship(
            id='rel-tl-al', actor_a='TL', actor_b='AL',
            type='alliance', strength=strength, is_active=True,
        ),
        Crisis(
            id='cascade-1', type='conflict', title='Testland Border Crisis',
            country='Testland', latitude=0, longitude=0, severity=70,
        ),
    ])
    db_session.commit()


def test_cascade_propagates_through_allied_actor(app_module, db_session):
    seed_alliance_scenario(db_session, strength=80)
    result = app_module.analyze_cascade('cascade-1', depth=2, threshold=50)

    assert result is not None
    assert result['initial_crisis'] == 'Testland Border Crisis'
    assert result['total_steps'] >= 1
    first_step_actors = result['steps'][0]['actors']
    assert 'AL' in first_step_actors


def test_cascade_respects_threshold(app_module, db_session):
    # Relationship strength (80) is below the threshold (90), so it should
    # never enter the propagation graph and no steps should be produced.
    seed_alliance_scenario(db_session, strength=80)
    result = app_module.analyze_cascade('cascade-1', depth=2, threshold=90)

    assert result is not None
    assert result['total_steps'] == 0
    assert result['steps'] == []


def test_cascade_missing_crisis_returns_none(app_module, db_session):
    result = app_module.analyze_cascade('does-not-exist')
    assert result is None


def test_cascade_probability_is_capped_at_one(app_module, db_session):
    seed_alliance_scenario(db_session, strength=100)
    result = app_module.analyze_cascade('cascade-1', depth=2, threshold=50)
    for step in result['steps']:
        assert 0 <= step['probability'] <= 1.0
    assert 0 <= result['total_cascade_probability'] <= 1.0


def test_city_named_country_resolves_via_location_map(app_module, db_session):
    # crisis.country is often a city/region name (e.g. ACLED's sample
    # fallback data uses "Tehran", not "Iran") rather than an exact
    # Actor.name match. NewsBasedCrisisDetector.LOCATION_MAP maps
    # 'tehran' -> {'country': 'Iran'}, so an actor named 'Iran' should be
    # found as the initial actor instead of falling through to the
    # geographic-proximity fallback.
    db_session.add_all([
        Actor(id='IR', name='Iran', category='STATE', latitude=32, longitude=53),
        Actor(id='RU', name='Russia', category='STATE', latitude=60, longitude=90),
        Relationship(
            id='rel-ir-ru', actor_a='IR', actor_b='RU',
            type='alliance', strength=80, is_active=True,
        ),
        Crisis(
            id='cascade-city', type='conflict', title='Tehran Unrest',
            country='Tehran', latitude=35.6892, longitude=51.3890, severity=70,
        ),
    ])
    db_session.commit()

    result = app_module.analyze_cascade('cascade-city', depth=2, threshold=50)
    assert result is not None
    assert result['total_steps'] >= 1
    assert 'RU' in result['steps'][0]['actors']


def test_affected_regions_reflects_real_actor_regions(app_module, db_session):
    # Actor.region is a real column now (see models.py) — affected_regions
    # used to always be [] regardless of which actors were involved,
    # because no such column existed at all.
    db_session.add_all([
        Actor(id='TL', name='Testland', region='Testregion', category='STATE', latitude=0, longitude=0),
        Actor(id='AL', name='Ally Nation', region='Allyregion', category='STATE', latitude=1, longitude=1),
        Relationship(
            id='rel-tl-al', actor_a='TL', actor_b='AL',
            type='alliance', strength=80, is_active=True,
        ),
        Crisis(
            id='cascade-region', type='conflict', title='Testland Border Crisis',
            country='Testland', latitude=0, longitude=0, severity=70,
        ),
    ])
    db_session.commit()

    result = app_module.analyze_cascade('cascade-region', depth=2, threshold=50)
    assert result['affected_regions'] == ['Allyregion']


def test_affected_regions_omits_actors_with_no_region(app_module, db_session):
    # seed_alliance_scenario's actors don't set `region` — affected_regions
    # must skip them (None) rather than crash or include a null entry.
    seed_alliance_scenario(db_session, strength=80)
    result = app_module.analyze_cascade('cascade-1', depth=2, threshold=50)
    assert result['affected_regions'] == []
