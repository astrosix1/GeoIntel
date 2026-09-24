"""
Tests for the forecast `method` field — added so a real stored Forecast
(method: Bayesian/Expert/Historical/ML) is distinguishable from the
heuristic severity-arithmetic fallback (_generate_static_forecasts), which
previously rendered as unlabeled, precise-looking percentages with nothing
telling the reader it wasn't a real model.
"""
from types import SimpleNamespace

from models import Forecast


def make_crisis(severity=70, ctype='conflict', country='Testland'):
    return SimpleNamespace(severity=severity, type=ctype, country=country)


def test_static_forecasts_are_labeled_heuristic(app_module):
    crisis = make_crisis()
    forecasts = app_module._generate_static_forecasts(crisis)
    assert len(forecasts) > 0
    assert all(f['method'] == 'heuristic' for f in forecasts)


def test_static_forecast_bars_stay_in_bounds(app_module):
    crisis = make_crisis(severity=95)
    forecasts = app_module._generate_static_forecasts(crisis)
    for f in forecasts:
        assert 5 <= f['low'] <= 95
        assert 5 <= f['mid'] <= 95
        assert 5 <= f['high'] <= 95


def test_forecast_to_dict_includes_method():
    forecast = Forecast(
        id='fc-1', crisis_id='c-1', question='Will X happen?',
        prob_unlikely=50, prob_possible=30, prob_likely=20,
        confidence=60, method='Bayesian',
    )
    d = forecast.to_dict()
    assert d['method'] == 'Bayesian'
