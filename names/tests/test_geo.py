"""geo.py: where North Frisia is, and how far apart two points are."""

from __future__ import annotations

import pytest

from frasch import geo


@pytest.mark.parametrize(
    "lon, lat",
    [
        (8.84, 54.79),  # Niebüll
        (8.32, 55.02),  # List auf Sylt
        (7.888, 54.182),  # Helgoland, its roads too (the matcher's box always had it)
    ],
)
def test_north_frisia_holds_its_places(lon: float, lat: float) -> None:
    assert geo.in_north_frisia(lon, lat)


@pytest.mark.parametrize(
    "lon, lat",
    [
        (9.99, 53.55),  # Hamburg
        (8.45, 55.47),  # Esbjerg
        (None, None),  # an object without a position
    ],
)
def test_north_frisia_leaves_out_the_rest(lon: float | None, lat: float | None) -> None:
    assert not geo.in_north_frisia(lon, lat)


def test_one_degree_of_latitude_is_about_111_km() -> None:
    assert geo.haversine(8.0, 54.0, 8.0, 55.0) == pytest.approx(111.19, abs=0.01)


def test_the_distance_to_an_unknown_position_is_unknown() -> None:
    assert geo.haversine(8.0, 54.0, None, None) is None
