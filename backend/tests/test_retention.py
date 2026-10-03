"""services/retention.py — old events are archived (is_active=False), never
deleted, and curated/scheduled entries are left alone."""
from datetime import datetime, timedelta

import pytest

from models import Crisis
from services.retention import archive_old_crises


@pytest.fixture(autouse=True)
def clean_crises(db_session):
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    db_session.query(Crisis).delete()
    db_session.commit()


def seed(db_session, id, age_days, source='GDELT', date_scheduled=None, status='active', is_active=True):
    db_session.add(Crisis(
        id=id, type='conflict', title=f'Crisis {id}', country='Testland',
        latitude=0, longitude=0, source=source, is_active=is_active,
        date_start=datetime.utcnow() - timedelta(days=age_days),
        date_scheduled=date_scheduled, status=status,
    ))
    db_session.commit()


def active_ids(db_session):
    db_session.expire_all()
    return {c.id for c in db_session.query(Crisis).filter(Crisis.is_active == True)}  # noqa: E712


def test_archives_old_rows_and_keeps_recent_ones(app_module, db_session):
    seed(db_session, 'old', age_days=10)
    seed(db_session, 'recent', age_days=2)
    assert archive_old_crises() == 1
    assert active_ids(db_session) == {'recent'}


def test_archived_rows_are_kept_not_deleted(app_module, db_session):
    seed(db_session, 'old', age_days=10)
    archive_old_crises()
    db_session.expire_all()
    row = db_session.query(Crisis).filter(Crisis.id == 'old').one()
    assert row.is_active is False


def test_boundary_just_inside_the_window_is_kept(app_module, db_session):
    seed(db_session, 'edge', age_days=6.9)
    assert archive_old_crises() == 0
    assert active_ids(db_session) == {'edge'}


def test_curated_entries_are_never_archived(app_module, db_session):
    seed(db_session, 'curated', age_days=60, source='CURATED')
    assert archive_old_crises() == 0
    assert active_ids(db_session) == {'curated'}


def test_scheduled_and_upcoming_events_are_never_archived(app_module, db_session):
    seed(db_session, 'election', age_days=60, date_scheduled=datetime.utcnow() + timedelta(days=30))
    seed(db_session, 'summit', age_days=60, status='upcoming')
    assert archive_old_crises() == 0
    assert active_ids(db_session) == {'election', 'summit'}


def test_rows_with_no_source_are_archived_like_any_other(app_module, db_session):
    seed(db_session, 'nosource', age_days=10, source=None)
    assert archive_old_crises() == 1


def test_is_idempotent(app_module, db_session):
    seed(db_session, 'old', age_days=10)
    assert archive_old_crises() == 1
    assert archive_old_crises() == 0


def test_custom_window(app_module, db_session):
    seed(db_session, 'three', age_days=3)
    assert archive_old_crises(days=2) == 1
