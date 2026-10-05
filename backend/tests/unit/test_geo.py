import pytest

from app.services.geo import haversine_m

LAGOS = (6.428100, 3.421900)
ABUJA = (9.056300, 7.498500)


def test_same_point_is_zero():
    assert haversine_m(*LAGOS, *LAGOS) == 0


def test_lagos_to_abuja_is_about_530_km():
    assert haversine_m(*LAGOS, *ABUJA) == pytest.approx(530_000, rel=0.02)


def test_symmetric():
    assert haversine_m(*LAGOS, *ABUJA) == pytest.approx(haversine_m(*ABUJA, *LAGOS))


def test_short_distances_are_accurate():
    # 0.001 degree of latitude is ~111 m everywhere.
    assert haversine_m(6.428100, 3.4219, 6.429100, 3.4219) == pytest.approx(111.2, abs=0.5)


def test_antipodes_do_not_crash():
    assert haversine_m(0, 0, 0, 180) == pytest.approx(20_015_000, rel=0.001)
