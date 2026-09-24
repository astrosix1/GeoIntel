"""
Tests for get_economic_impact() in app.py.

The old `estimated_impact` block (trade_disruption_percent, etc.) was pure
severity arithmetic decoupled from the real WorldBank-sourced EconomicData
sitting right next to it in the same response. `economic_profile` replaces
it with a real ratio computed from that actual data, and is None — not a
fabricated fallback — when no EconomicData row exists for the crisis's
country.
"""
import pytest

from models import Crisis, EconomicData


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    db_session.query(EconomicData).delete()
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(EconomicData).delete()
    db_session.query(Crisis).delete()
    db_session.commit()


def seed_crisis(db_session, country='US', severity=70, ctype='economic'):
    db_session.add(Crisis(
        id='econ-1', type=ctype, title='Test Crisis',
        country=country, latitude=0, longitude=0, severity=severity,
    ))
    db_session.commit()


def test_no_economic_data_gives_none_profile(app_module, db_session):
    seed_crisis(db_session, country='US')
    result = app_module.get_economic_impact('econ-1')
    assert result['economic_profile'] is None
    assert result['economic_data'] == {}


def test_real_economic_data_produces_real_profile(app_module, db_session):
    seed_crisis(db_session, country='US')
    db_session.add(EconomicData(
        id='ed-1', country_code='US', gdp=25000, gdp_growth=2.1,
        exports=2000, imports=3000, inflation=3.5, unemployment=4.0,
        trade_balance=-1000, year=2024,
    ))
    db_session.commit()

    result = app_module.get_economic_impact('econ-1')
    profile = result['economic_profile']
    assert profile is not None
    assert profile['trade_openness_percent_of_gdp'] == pytest.approx((2000 + 3000) / 25000 * 100, rel=1e-6)
    assert profile['trade_balance'] == -1000
    assert profile['unemployment'] == 4.0


def test_sectors_key_is_renamed_and_honest(app_module, db_session):
    seed_crisis(db_session, country='US', ctype='conflict')
    result = app_module.get_economic_impact('econ-1')
    assert 'sectors_typically_exposed' in result
    assert 'estimated_impact' not in result
    assert isinstance(result['sectors_typically_exposed'], list)
    assert len(result['sectors_typically_exposed']) > 0


def test_missing_crisis_returns_none(app_module, db_session):
    result = app_module.get_economic_impact('does-not-exist')
    assert result is None
