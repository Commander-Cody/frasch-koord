"""dialect_areas.py: the "smallest area containing a point wins" rule of the
area lookup, the dialect spoken where an object lies (`dialect_at`, the one
answer the injector and the search index share, #24), and the rules of the
area list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from frasch import dialect_areas, dialects, tables
from frasch.dialect_areas import dialect_at
from frasch.errors import Problem
from frasch.objects import LocatedObject
from conftest import REGISTRY


@pytest.fixture(scope="module")
def reg() -> dialects.Registry:
    return REGISTRY


# ------------------------------------------------------------- AreaIndex ---
# Nested squares, like the Hamburger Hallig (Halligfriesisch) inside the
# municipality Reußenköge (Mooring)
OUTER = box(8.80, 54.55, 8.95, 54.65)  # Reußenköge
INNER = box(8.82, 54.58, 8.86, 54.60)  # Hamburger Hallig


@pytest.mark.parametrize(
    "polygons",
    [
        [("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)],
        [("frr-x-hallig", INNER), ("frr-x-mooring", OUTER)],
    ],
    ids=["large-first", "small-first"],
)
def test_the_smallest_area_containing_the_point_wins(
    polygons: list[tuple[str, BaseGeometry]],
) -> None:
    areas = dialect_areas.AreaIndex(polygons)
    assert areas.lookup(8.84, 54.59) == "frr-x-hallig"


def test_a_point_only_in_the_large_area_gets_its_dialect() -> None:
    areas = dialect_areas.AreaIndex([("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)])
    assert areas.lookup(8.90, 54.62) == "frr-x-mooring"


def test_a_point_outside_every_area_has_no_dialect() -> None:
    # Nordstrand has no Frisian area at all
    areas = dialect_areas.AreaIndex([("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)])
    assert areas.lookup(8.87, 54.49) is None


def test_a_point_on_the_outline_is_inside() -> None:
    areas = dialect_areas.AreaIndex([("frr-x-mooring", OUTER)])
    assert areas.lookup(8.80, 54.60) == "frr-x-mooring"


def test_lookup_takes_coordinate_strings() -> None:
    areas = dialect_areas.AreaIndex([("frr-x-mooring", OUTER)])
    assert areas.lookup("8.90", "54.62") == "frr-x-mooring"


def test_an_empty_index_knows_no_dialect() -> None:
    assert dialect_areas.AreaIndex([]).lookup(8.84, 54.59) is None


# -------------------------------------------------------------- area_rows ---
# A node can never be a polygon, and `local/` names an object our own
# curation.csv invents -- neither belongs in an OSM-boundary area list (#24).
def test_area_rows_rejects_a_node_reference(tmp_path: Path, reg: dialects.Registry) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\nfrr-x-mooring,node/1,A node,\n", encoding="utf-8")
    rows, problems = dialect_areas.area_rows(str(areas), reg)
    assert rows == []
    assert problems == [
        Problem(str(areas), 2, "node/1: only way/ or relation/ references are allowed here")
    ]


def test_area_rows_rejects_a_local_reference(tmp_path: Path, reg: dialects.Registry) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\nfrr-x-mooring,local/some-slug,A local place,\n", encoding="utf-8"
    )
    rows, problems = dialect_areas.area_rows(str(areas), reg)
    assert rows == []
    assert problems == [
        Problem(
            str(areas), 2, "local/some-slug: only way/ or relation/ references are allowed here"
        )
    ]


def test_area_rows_still_accepts_way_and_relation_references(
    tmp_path: Path, reg: dialects.Registry
) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\nfrr-x-mooring,way/1;relation/2,Fine,\n", encoding="utf-8"
    )
    rows, problems = dialect_areas.area_rows(str(areas), reg)
    assert problems == []
    assert rows[0]["refs"] == [("w", 1), ("r", 2)]


# What a spreadsheet does to the file is reported as for the other three
# hand-edited files (#92): the area list used to have a reader of its own.
def test_area_rows_reports_a_semicolon_separated_export_as_such(
    tmp_path: Path, reg: dialects.Registry
) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect;osm;name;note\nfrr-x-mooring;relation/1;Fine;\n", encoding="utf-8")
    _, problems = dialect_areas.area_rows(str(areas), reg)
    assert problems == [Problem(str(areas), 1, tables.SEMICOLON_SEPARATED)]


def test_area_rows_reports_a_row_with_the_wrong_number_of_cells(
    tmp_path: Path, reg: dialects.Registry
) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\nfrr-x-mooring,relation/1,Fine\n", encoding="utf-8")
    _, problems = dialect_areas.area_rows(str(areas), reg)
    assert problems == [
        Problem(str(areas), 2, "3 cells, the header has 4 (a comma too many or too few?)")
    ]


def test_area_rows_reports_a_problem_after_a_blank_line_on_its_own_line(
    tmp_path: Path, reg: dialects.Registry
) -> None:
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\nfrr-x-mooring,relation/1,Fine,\n\nfrr-x-mooring,node/2,A node,\n",
        encoding="utf-8",
    )
    _, problems = dialect_areas.area_rows(str(areas), reg)
    assert [p.line for p in problems] == [4]


def test_area_rows_needs_every_column_of_the_file(tmp_path: Path, reg: dialects.Registry) -> None:
    # `name` and `note` are what the review overlay shows of a row.
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm\nfrr-x-mooring,relation/1\n", encoding="utf-8")
    _, problems = dialect_areas.area_rows(str(areas), reg)
    assert problems == [Problem(str(areas), 1, "missing column(s) name, note")]


# --------------------------------------------------------------- dialect_at ---
def ring(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


@pytest.fixture
def area_index(tmp_path: Path) -> dialect_areas.AreaIndex:
    """Reußenköge (Mooring) with the Hamburger Hallig (Halligfriesisch)
    inside it, and a strip of Langeneß covering only part of Oland."""
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"dialect": tag},
                "geometry": {"type": "Polygon", "coordinates": ring(*bounds)},
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
    return dialect_areas.AreaIndex.from_geojson(str(path))


def test_the_smallest_area_around_an_object_wins(area_index: dialect_areas.AreaIndex) -> None:
    assert dialect_at({"lon": 8.84, "lat": 54.59}, area_index) == "frr-x-hallig"


def test_outside_every_area_there_is_no_dialect(area_index: dialect_areas.AreaIndex) -> None:
    assert dialect_at({"lon": 8.0, "lat": 54.0}, area_index) is None


def test_the_outline_point_answers_when_the_inside_point_misses(
    area_index: dialect_areas.AreaIndex,
) -> None:
    oland: LocatedObject = {"lon": 8.65, "lat": 54.61, "outline": [8.61, 54.61]}
    assert dialect_at(oland, area_index) == "frr-x-hallig"


def test_a_district_spans_dialects_and_gets_none(area_index: dialect_areas.AreaIndex) -> None:
    kreis: LocatedObject = {"lon": 8.84, "lat": 54.59, "admin_level": 6}
    assert dialect_at(kreis, area_index) is None


def test_a_municipality_gets_its_dialect(area_index: dialect_areas.AreaIndex) -> None:
    gemeinde: LocatedObject = {"lon": 8.84, "lat": 54.59, "admin_level": 8}
    assert dialect_at(gemeinde, area_index) == "frr-x-hallig"
