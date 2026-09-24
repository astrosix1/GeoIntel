"""
Tests for DataAggregator.sync_actor_power_stats() and
WorldBankConnector.derive_country_codes() in data_sources.py.

Actor.military_power/economic_power/political_influence/
technological_capability used to default to 50 for every actor (a Column-
level default, never overridden by init_actors()) — identical fabricated
stats presented as if they were assessed per-actor. economic_power is now
derived from real WorldBank GDP data already sitting in EconomicData; the
other three have no real data source anywhere in this app and are
explicitly cleared to None rather than left fabricated.
"""
import pytest

from models import Actor, EconomicData
from data_sources import DataAggregator, WorldBankConnector, ACTOR_WB_COUNTRY_OVERRIDES


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    db_session.query(EconomicData).delete()
    db_session.query(Actor).delete()
    db_session.commit()
    yield
    db_session.query(EconomicData).delete()
    db_session.query(Actor).delete()
    db_session.commit()


def seed_actor(db_session, actor_id, name, military=99, economic=99, political=99, technological=99):
    # Seed with the OLD fabricated-looking values (as if inserted before the
    # Column default was removed) to prove sync_actor_power_stats() clears
    # them rather than merely never-setting them.
    db_session.add(Actor(
        id=actor_id, name=name, category='STATE', latitude=0, longitude=0,
        military_power=military, economic_power=economic,
        political_influence=political, technological_capability=technological,
    ))
    db_session.commit()


def test_no_actors_is_a_noop(app_module, db_session):
    DataAggregator.sync_actor_power_stats(db_session)  # should not raise
    assert db_session.query(Actor).count() == 0


def test_stats_with_no_gdp_data_are_cleared_to_none(app_module, db_session):
    seed_actor(db_session, 'US', 'United States')
    DataAggregator.sync_actor_power_stats(db_session)
    db_session.commit()

    actor = db_session.query(Actor).filter(Actor.id == 'US').first()
    assert actor.military_power is None
    assert actor.political_influence is None
    assert actor.technological_capability is None
    assert actor.economic_power is None  # no EconomicData row exists yet


def test_economic_power_derived_from_real_gdp_and_others_stay_none(app_module, db_session):
    seed_actor(db_session, 'US', 'United States')
    seed_actor(db_session, 'CN', 'China')
    db_session.add_all([
        EconomicData(id='ed-us', country_code='US', gdp=25000, year=2024),
        EconomicData(id='ed-cn', country_code='CN', gdp=18000, year=2024),
    ])
    db_session.commit()

    DataAggregator.sync_actor_power_stats(db_session)
    db_session.commit()

    us = db_session.query(Actor).filter(Actor.id == 'US').first()
    cn = db_session.query(Actor).filter(Actor.id == 'CN').first()

    # Larger real GDP should score higher, but never fabricated/identical.
    assert us.economic_power is not None
    assert cn.economic_power is not None
    assert us.economic_power > cn.economic_power
    assert 0 <= us.economic_power <= 100
    assert 0 <= cn.economic_power <= 100

    # The three unsupported dimensions must always be None, regardless of
    # whether real economic data exists.
    for actor in (us, cn):
        assert actor.military_power is None
        assert actor.political_influence is None
        assert actor.technological_capability is None


def test_non_iso_actor_ids_resolve_via_override_map(app_module, db_session):
    # North Korea's Actor id ('NK') isn't a real ISO/WorldBank country code;
    # its EconomicData is stored under the real code ('KP') per
    # ACTOR_WB_COUNTRY_OVERRIDES.
    assert ACTOR_WB_COUNTRY_OVERRIDES['NK'] == 'KP'
    seed_actor(db_session, 'NK', 'North Korea')
    db_session.add(EconomicData(id='ed-kp', country_code='KP', gdp=20, year=2024))
    db_session.commit()

    DataAggregator.sync_actor_power_stats(db_session)
    db_session.commit()

    nk = db_session.query(Actor).filter(Actor.id == 'NK').first()
    assert nk.economic_power is not None


def test_derive_country_codes_uses_real_actor_roster(app_module, db_session):
    seed_actor(db_session, 'US', 'United States')
    seed_actor(db_session, 'NK', 'North Korea')
    codes = WorldBankConnector.derive_country_codes(db_session)
    assert 'US' in codes
    assert 'KP' in codes  # translated via the override map, not the raw 'NK'
    assert 'NK' not in codes


def test_derive_country_codes_falls_back_when_no_actors(app_module, db_session):
    codes = WorldBankConnector.derive_country_codes(db_session)
    assert codes == ['US', 'CN', 'RU', 'JP', 'DE', 'IN']
