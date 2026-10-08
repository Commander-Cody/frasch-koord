"""objects.py: which dialect is spoken where an object of the objects file
(names/osm_objects.json) lies -- the one answer the injector (tiles) and the
search index share (#24)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import dialects, placelist
from frasch.errors import PipelineError
from frasch.objects import LocatedObject, Objects, dialect_at, objects_json, point, read_objects
from frasch.provenance import Stamp
from conftest import REGISTRY


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


# ----------------------------------------------------------- the file itself ---
NAIBEL: LocatedObject = {"lon": 8.83, "lat": 54.79}
NO_EXTRACTS = Stamp({}, [])


def read_back(objects: Objects, tmp_path: Path) -> Objects:
    """`objects` written as an objects file and read again."""
    path = tmp_path / "osm_objects.json"
    path.write_text(objects_json(objects), encoding="utf-8")
    return read_objects(str(path))


def test_the_file_keeps_the_references_no_extract_held(tmp_path: Path) -> None:
    objects = Objects({("n", 1): NAIBEL}, NO_EXTRACTS, frozenset({("w", 99)}))
    assert read_back(objects, tmp_path).not_found == {("w", 99)}


def test_a_file_whose_references_were_all_found_stays_as_it_was_before_it_kept_them() -> None:
    assert objects_json(Objects({("n", 1): NAIBEL}, NO_EXTRACTS)) == (
        '{"built_from":{"extracts":[]},\n"objects":{\n"node/1":{"lon":8.83,"lat":54.79}\n}}\n'
    )


def test_the_references_asked_for_are_those_found_and_those_not_found() -> None:
    objects = Objects({("n", 1): NAIBEL}, NO_EXTRACTS, frozenset({("w", 99)}))
    assert objects.asked == {("n", 1), ("w", 99)}


def test_the_references_without_an_object_are_missing_in_the_files_order() -> None:
    objects = Objects({("n", 1): NAIBEL}, NO_EXTRACTS, frozenset({("w", 99)}))
    wanted = {("r", 7), ("w", 99), ("n", 1), ("n", 5)}
    assert objects.missing(wanted) == [("n", 5), ("w", 99), ("r", 7)]


def test_a_file_without_a_stamp_stops_the_reader_with_how_to_rebuild_it(tmp_path: Path) -> None:
    path = tmp_path / "osm_objects.json"
    path.write_text(json.dumps({"objects": {}}), encoding="utf-8")
    with pytest.raises(
        PipelineError, match="was built from -- build it with `just rebuild objects`"
    ):
        read_objects(str(path))


# -------------------------------------------------- the object of a row ---
def test_a_point_is_an_object_at_its_position_with_the_facts_given() -> None:
    assert point(8.83, 54.79, name_frr="Naibel") == {
        "lon": 8.83,
        "lat": 54.79,
        "name_frr": "Naibel",
    }


def place(**cells: str) -> placelist.PlaceRow:
    return placelist.PlaceRow({c: "" for c in placelist.columns(REGISTRY)} | cells, 2)


NORDWARW = place(id="nordwarw", kind="warft", mooring="Nordwärw", osm="way/7; node/1")
OCKHOLM: LocatedObject = {"lon": 8.84, "lat": 54.67}
LOCATED = Objects({("n", 1): NAIBEL, ("w", 7): OCKHOLM}, NO_EXTRACTS)


def test_the_object_of_a_row_is_that_of_its_first_reference() -> None:
    assert LOCATED.for_row(NORDWARW, {}, REGISTRY) == OCKHOLM


WAASTERHIAS = place(
    id="waasterhias",
    kind="settlement",
    oomrang="Waasterhias",
    de="Westerheide",
    osm="local/westerheide-amrum",
)


def test_the_object_of_a_place_osm_does_not_have_is_the_point_the_injector_adds() -> None:
    # at its curation position, with the generic name the point gets: the German one
    positions = {"westerheide-amrum": (8.34019, 54.65097)}
    assert LOCATED.for_row(WAASTERHIAS, positions, REGISTRY) == {
        "lon": 8.34019,
        "lat": 54.65097,
        "name": "Westerheide",
    }


def test_a_place_osm_does_not_have_needs_a_position_in_the_curation() -> None:
    with pytest.raises(PipelineError, match=r"waasterhias \(line 2\): local/westerheide-amrum"):
        LOCATED.for_row(WAASTERHIAS, {}, REGISTRY)


def test_a_row_keyed_by_its_wikidata_id_alone_has_no_object() -> None:
    denmark = place(id="daanemark", kind="country", mooring="Däänemark", wikidata="Q35")
    assert LOCATED.for_row(denmark, {}, REGISTRY) is None
