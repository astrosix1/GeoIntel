"""Great-circle distance helper."""
import pytest

from services.geo import distance_km


def test_same_point_is_zero():
    assert distance_km(10, 20, 10, 20) == 0


def test_london_to_paris():
    assert distance_km(51.5074, -0.1278, 48.8566, 2.3522) == pytest.approx(343.6, abs=1.5)


def test_is_symmetric():
    assert distance_km(1, 2, 30, 40) == pytest.approx(distance_km(30, 40, 1, 2))


def test_across_the_antimeridian_is_short():
    # 0.2 degrees of longitude on the equator, not 359.8
    assert distance_km(0, 179.9, 0, -179.9) == pytest.approx(22.2, abs=0.3)


def test_across_the_pole_is_short():
    assert distance_km(89.9, 0, 89.9, 180) == pytest.approx(22.2, abs=0.3)


def test_antipodes_are_half_the_circumference():
    assert distance_km(0, 0, 0, 180) == pytest.approx(20015, abs=5)
