"""
Tests for the Forecast model's `method` field — distinguishes a real stored
forecast (method: Bayesian/Expert/Historical/ML) from the old heuristic
severity-arithmetic fallback. That fallback (_generate_static_forecasts)
and the rest of the Forecast tab's UI/API surface were removed in a later
phase (the Forecast DB table itself was deliberately kept — see that
phase's plan — to be rebuilt on a real model later), so only the model-level
test below still applies; the two tests that called the removed function
directly were removed along with it.
"""
from models import Forecast


def test_forecast_to_dict_includes_method():
    forecast = Forecast(
        id='fc-1', crisis_id='c-1', question='Will X happen?',
        prob_unlikely=50, prob_possible=30, prob_likely=20,
        confidence=60, method='Bayesian',
    )
    d = forecast.to_dict()
    assert d['method'] == 'Bayesian'
