"""
Tests for analyze_escalation() in app.py.

analyze_escalation() used to fabricate a "7-day trend" via deterministic
backward extrapolation from a single current severity value — no real
history existed anywhere. It now queries real CrisisSnapshot rows (see
DataAggregator.snapshot_severity_history in data_sources.py, populated once
per active crisis on every scheduled sync). These tests seed real
CrisisSnapshot rows via db_session and check the trend/velocity computed
from them, plus the honest 'insufficient_data' degradation when fewer than
2 snapshots exist yet for a crisis.
"""
from datetime import datetime, timedelta

import pytest

from models import Crisis, CrisisSnapshot


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    """Each test seeds exactly the rows it needs and cleans up afterwards
    to stay independent of test order (same pattern as test_cascade.py)."""
    db_session.query(CrisisSnapshot).delete()
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(CrisisSnapshot).delete()
    db_session.query(Crisis).delete()
    db_session.commit()


def seed_crisis(db_session, severity=50):
    db_session.add(Crisis(
        id='esc-1', type='conflict', title='Test Crisis',
        country='Testland', latitude=0, longitude=0, severity=severity,
    ))
    db_session.commit()


def seed_snapshots(db_session, severities, hours_apart=24):
    """severities: oldest-to-newest list of severity readings, `hours_apart`
    hours apart (default 24h — one per day, matching the real hourly-sync
    cadence at a readable scale for a test)."""
    now = datetime.utcnow()
    n = len(severities)
    for i, sev in enumerate(severities):
        recorded_at = now - timedelta(hours=(n - 1 - i) * hours_apart)
        db_session.add(CrisisSnapshot(crisis_id='esc-1', severity=sev, recorded_at=recorded_at))
    db_session.commit()


def test_missing_crisis_returns_none(app_module, db_session):
    result = app_module.analyze_escalation('does-not-exist')
    assert result is None


def test_zero_snapshots_is_insufficient_data(app_module, db_session):
    seed_crisis(db_session, severity=90)
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'insufficient_data'
    assert result['velocity'] is None
    assert result['current_severity'] == 90
    assert result['history'] == []


def test_one_snapshot_is_insufficient_data(app_module, db_session):
    seed_crisis(db_session, severity=90)
    seed_snapshots(db_session, [90])
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'insufficient_data'
    assert result['velocity'] is None
    assert len(result['history']) == 1


def test_rising_severity_is_escalating(db_session, app_module):
    seed_crisis(db_session, severity=90)
    seed_snapshots(db_session, [50, 90], hours_apart=24)
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'escalating'
    assert result['velocity'] > 5
    assert result['severity_change'] == 40
    assert result['warning'] is not None


def test_falling_severity_is_deescalating(db_session, app_module):
    seed_crisis(db_session, severity=20)
    seed_snapshots(db_session, [80, 20], hours_apart=24)
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'de-escalating'
    assert result['velocity'] < -5
    assert result['severity_change'] == -60


def test_flat_severity_is_stable(db_session, app_module):
    seed_crisis(db_session, severity=50)
    seed_snapshots(db_session, [50, 50, 50], hours_apart=24)
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'stable'
    assert result['warning'] is None


def test_small_change_stays_within_stable_band(db_session, app_module):
    # A 3-point rise over a full day is real movement but not enough to
    # call "escalating" (velocity threshold is 5 pts/day) — this guards
    # against the bucket boundaries drifting from noise-level changes.
    seed_crisis(db_session, severity=53)
    seed_snapshots(db_session, [50, 53], hours_apart=24)
    result = app_module.analyze_escalation('esc-1')
    assert result['trend'] == 'stable'


def test_history_is_ordered_oldest_to_newest(db_session, app_module):
    seed_crisis(db_session, severity=90)
    seed_snapshots(db_session, [10, 50, 90], hours_apart=24)
    result = app_module.analyze_escalation('esc-1')
    dates = [h['date'] for h in result['history']]
    assert dates == sorted(dates)


def test_passing_preloaded_crisis_skips_lookup(db_session, app_module):
    seed_crisis(db_session, severity=90)
    seed_snapshots(db_session, [50, 90], hours_apart=24)
    crisis = db_session.query(Crisis).filter(Crisis.id == 'esc-1').first()
    result = app_module.analyze_escalation('esc-1', _crisis=crisis)
    assert result['trend'] == 'escalating'
    assert result['current_severity'] == 90
