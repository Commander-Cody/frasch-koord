"""objects.py: the objects file (names/osm_objects.json) -- what it keeps,
how it is written and read back -- and an object that is a point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch.errors import PipelineError
from frasch.objects import LocatedObject, Objects, objects_json, point, read_objects
from frasch.provenance import Stamp


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


# ------------------------------------------------------------------ a point ---
def test_a_point_is_an_object_at_its_position_with_the_facts_given() -> None:
    assert point(8.83, 54.79, name_frr="Naibel") == {
        "lon": 8.83,
        "lat": 54.79,
        "name_frr": "Naibel",
    }
