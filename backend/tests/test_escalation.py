"""
Tests for analyze_escalation() in app.py.

analyze_escalation() accepts an already-loaded Crisis row via `_crisis`,
so these tests build a Crisis in memory (never committed to the DB) and
check the trend/warning it derives from the row's `severity`.
"""
from datetime import datetime

from models import Crisis


def make_crisis(severity, date_start=None):
    return Crisis(
        id='test-1',
        type='conflict',
        title='Test Crisis',
        country='Testland',
        latitude=0,
        longitude=0,
        severity=severity,
        date_start=date_start or datetime.utcnow(),
    )


def test_high_severity_crisis_shows_escalating_trend(app_module):
    crisis = make_crisis(severity=90)
    result = app_module.analyze_escalation('test-1', _crisis=crisis)
    assert result['trend'] == 'escalating'
    assert result['warning'] is not None
    assert result['current_severity'] == 90
    assert len(result['history']) == 7


def test_low_severity_crisis_shows_stable_trend(app_module):
    crisis = make_crisis(severity=20)
    result = app_module.analyze_escalation('test-1', _crisis=crisis)
    assert result['trend'] == 'stable'
    assert result['warning'] is None


def test_history_is_ordered_oldest_to_newest(app_module):
    crisis = make_crisis(severity=90)
    result = app_module.analyze_escalation('test-1', _crisis=crisis)
    dates = [h['date'] for h in result['history']]
    assert dates == sorted(dates)


def test_missing_crisis_returns_none(app_module):
    result = app_module.analyze_escalation('does-not-exist')
    assert result is None
