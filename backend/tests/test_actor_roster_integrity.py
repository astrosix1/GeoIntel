"""
Integrity tests for the curated actor/relationship roster in
data_sources.py (init_actors, init_relationships). This is real
hand-curated content (Phase 2 of the compendious-tool roadmap expanded it
from 8 to 68 actors), so these tests catch editing mistakes — duplicate
ids, a relationship referencing an actor that was renamed or removed — not
"real-world accuracy" itself.
"""
import pytest

from models import Actor, Relationship
import data_sources as ds


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    db_session.query(Relationship).delete()
    db_session.query(Actor).delete()
    db_session.commit()
    yield
    db_session.query(Relationship).delete()
    db_session.query(Actor).delete()
    db_session.commit()


def test_roster_has_at_least_50_actors(app_module, db_session):
    ds.init_actors()
    assert db_session.query(Actor).count() >= 50


def test_no_duplicate_actor_ids(app_module, db_session):
    ds.init_actors()
    ids = [a.id for a in db_session.query(Actor).all()]
    assert len(ids) == len(set(ids))


def test_no_duplicate_relationship_ids(app_module, db_session):
    ds.init_actors()
    ds.init_relationships()
    ids = [r.id for r in db_session.query(Relationship).all()]
    assert len(ids) == len(set(ids))


def test_every_relationship_references_a_real_actor(app_module, db_session):
    ds.init_actors()
    ds.init_relationships()
    actor_ids = {a.id for a in db_session.query(Actor).all()}
    dangling = [
        (r.id, r.actor_a, r.actor_b)
        for r in db_session.query(Relationship).all()
        if r.actor_a not in actor_ids or r.actor_b not in actor_ids
    ]
    assert dangling == []


def test_known_nuclear_states_are_marked_nuclear(app_module, db_session):
    ds.init_actors()
    actors = {a.id: a for a in db_session.query(Actor).all()}
    for aid in ('US', 'RU', 'CN', 'GB', 'FR', 'IN', 'PK', 'IL', 'NK'):
        assert actors[aid].is_nuclear is True
    # Spot-check large non-nuclear powers aren't fabricated as nuclear.
    assert actors['DE'].is_nuclear is False
    assert actors['JP'].is_nuclear is False


def test_new_actors_start_with_no_fabricated_power_stats(app_module, db_session):
    ds.init_actors()
    for actor in db_session.query(Actor).all():
        assert actor.military_power is None
        assert actor.economic_power is None
        assert actor.political_influence is None
        assert actor.technological_capability is None


def test_every_actor_has_a_real_region(app_module, db_session):
    # region backs analyze_cascade()'s affected_regions (Phase 3) — every
    # actor in the roster should have one, not just a handful.
    ds.init_actors()
    for actor in db_session.query(Actor).all():
        assert actor.region, f"{actor.id} ({actor.name}) has no region set"


def test_region_backfills_onto_already_existing_actor_rows(app_module, db_session):
    # Simulates an actor row inserted before the `region` column existed
    # (skip-if-exists in init_actors() would otherwise never touch it again).
    db_session.add(Actor(id='US', name='United States', category='STATE', latitude=0, longitude=0))
    db_session.commit()
    assert db_session.query(Actor).filter(Actor.id == 'US').first().region is None

    ds.init_actors()
    db_session.expire_all()
    assert db_session.query(Actor).filter(Actor.id == 'US').first().region == 'North America'
