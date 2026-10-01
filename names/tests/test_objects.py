"""objects.py: which dialect is spoken where an object of the objects file
(names/osm_objects.json) lies -- the one answer the injector (tiles) and the
search index share (#24)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import dialects
from frasch.objects import LocatedObject, dialect_at


# --------------------------------------------------------------- dialect_at ---
def box(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


@pytest.fixture
def areas(tmp_path: Path) -> dialects.AreaIndex:
    """Reußenköge (Mooring) with the Hamburger Hallig (Halligfriesisch)
    inside it, and a strip of Langeneß covering only part of Oland."""
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"dialect": tag},
                "geometry": {"type": "Polygon", "coordinates": box(*bounds)},
            }
            for tag, bounds in [
                ("frr-x-mooring", (8.80, 54.55, 8.95, 54.63)),
                ("frr-x-hallig", (8.82, 54.58, 8.86, 54.605)),
                ("frr-x-hallig", (8.60, 54.60, 8.62, 54.62)),
            ]
        ],
    }
    path = tmp_path / "areas.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return dialects.AreaIndex.from_geojson(str(path))


def test_the_smallest_area_around_an_object_wins(areas: dialects.AreaIndex) -> None:
    assert dialect_at({"lon": 8.84, "lat": 54.59}, areas) == "frr-x-hallig"


def test_outside_every_area_there_is_no_dialect(areas: dialects.AreaIndex) -> None:
    assert dialect_at({"lon": 8.0, "lat": 54.0}, areas) is None


def test_the_outline_point_answers_when_the_inside_point_misses(areas: dialects.AreaIndex) -> None:
    oland: LocatedObject = {"lon": 8.65, "lat": 54.61, "outline": [8.61, 54.61]}
    assert dialect_at(oland, areas) == "frr-x-hallig"


def test_a_district_spans_dialects_and_gets_none(areas: dialects.AreaIndex) -> None:
    kreis: LocatedObject = {"lon": 8.84, "lat": 54.59, "admin_level": 6}
    assert dialect_at(kreis, areas) is None


def test_a_municipality_gets_its_dialect(areas: dialects.AreaIndex) -> None:
    gemeinde: LocatedObject = {"lon": 8.84, "lat": 54.59, "admin_level": 8}
    assert dialect_at(gemeinde, areas) == "frr-x-hallig"
