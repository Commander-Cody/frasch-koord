"""osmscan.py: the id-filtered passes over an extract -- only the objects
asked for, and what their geometry takes."""

from __future__ import annotations

from pathlib import Path

from frasch import osmscan
from frasch.paths import StrPath
from frasch.refs import OsmRef
from osm_fixture import write_extract


def extract(tmp_path: Path) -> str:
    return str(
        write_extract(
            tmp_path / "x.osm.pbf",
            nodes={
                1: ((8.0, 54.0), {}),
                2: ((8.1, 54.0), {"name": "Hüs"}),
                3: ((8.1, 54.1), {}),
                4: ((8.05, 54.05), {"place": "village"}),
            },
            ways={10: ([1, 2, 3, 1], {"natural": "coastline"}), 11: ([2, 3], {})},
            relations={
                20: (
                    [
                        ("w", 10, "outer"),
                        ("w", 11, "inner"),
                        ("n", 4, "label"),
                        ("n", 3, "admin_centre"),
                    ],
                    {"boundary": "administrative"},
                ),
                21: ([("w", 11, "")], {}),
                22: (
                    [
                        ("w", 11, "side_stream"),
                        ("n", 4, "spring"),
                        ("w", 10, "main_stream"),
                        ("w", 12, ""),
                    ],
                    {"type": "waterway"},
                ),
            },
        )
    )


def test_relations_come_with_their_rings_member_ways_label_and_tags(tmp_path: Path) -> None:
    assert osmscan.relations(extract(tmp_path), {20}) == {
        20: {
            "rings": {"outer": [10], "inner": [11]},
            "member_ways": [10, 11],
            "label": 4,
            "tags": {"boundary": "administrative"},
        }
    }


def test_a_member_without_a_role_is_an_outer_ring(tmp_path: Path) -> None:
    assert osmscan.relations(extract(tmp_path), {21})[21]["rings"] == {"outer": [11], "inner": []}


def test_member_ways_are_those_of_every_role_in_member_order(tmp_path: Path) -> None:
    assert osmscan.relations(extract(tmp_path), {22})[22]["member_ways"] == [11, 10, 12]


def test_ways_come_with_their_nodes_and_tags(tmp_path: Path) -> None:
    assert osmscan.ways(extract(tmp_path), {10}) == {
        10: {"nodes": [1, 2, 3, 1], "tags": {"natural": "coastline"}}
    }


def test_nodes_come_with_their_location_and_tags(tmp_path: Path) -> None:
    assert osmscan.nodes(extract(tmp_path), {2}) == {
        2: {"loc": (8.1, 54.0), "tags": {"name": "Hüs"}}
    }


def test_only_the_objects_asked_for_are_read(tmp_path: Path) -> None:
    path = extract(tmp_path)
    assert set(osmscan.nodes(path, {1, 3, 99})) == {1, 3}
    assert osmscan.ways(path, set()) == {}


def test_a_node_without_a_valid_location_is_left_out(tmp_path: Path) -> None:
    path = str(
        write_extract(
            tmp_path / "bad.osm.pbf", nodes={1: ((8.0, 54.0), {}), 2: ((200.0, 100.0), {})}
        )
    )
    assert set(osmscan.nodes(path, {1, 2})) == {1}


def test_an_extract_is_named_by_its_file_and_replication_timestamp(tmp_path: Path) -> None:
    pbf = write_extract(
        tmp_path / "denmark-latest.osm.pbf",
        nodes={1: ((8.5, 55.0), {})},
        timestamp="2026-09-22T20:22:59Z",
    )
    assert osmscan.extract_stamp(pbf) == {
        "file": "denmark-latest.osm.pbf",
        "replication_timestamp": "2026-09-22T20:22:59Z",
    }


def test_an_extract_without_a_timestamp_says_so(tmp_path: Path) -> None:
    pbf = write_extract(tmp_path / "x.osm.pbf", nodes={1: ((8.5, 55.0), {})})
    assert osmscan.extract_stamp(pbf)["replication_timestamp"] == ""


# ---------------------------------------------------------- read_geometry ---
def test_a_relation_is_read_with_its_member_ways_and_their_nodes(tmp_path: Path) -> None:
    geometry = osmscan.read_geometry(extract(tmp_path), {("r", 21)})
    assert (set(geometry.relations), set(geometry.ways), set(geometry.nodes)) == (
        {21},
        {11},
        {2, 3},
    )


def test_a_referenced_way_is_read_with_its_nodes(tmp_path: Path) -> None:
    geometry = osmscan.read_geometry(extract(tmp_path), {("w", 11)})
    assert (set(geometry.ways), set(geometry.nodes)) == ({11}, {2, 3})


def test_a_referenced_node_is_read(tmp_path: Path) -> None:
    geometry = osmscan.read_geometry(extract(tmp_path), {("n", 4)})
    assert geometry.nodes == {4: {"loc": (8.05, 54.05), "tags": {"place": "village"}}}


def test_the_label_node_of_a_relation_is_read_too(tmp_path: Path) -> None:
    geometry = osmscan.read_geometry(extract(tmp_path), {("r", 20)})
    assert 4 in geometry.nodes


def test_relations_read_before_ride_along_with_their_ways_and_nodes(tmp_path: Path) -> None:
    path = extract(tmp_path)
    geometry = osmscan.read_geometry(path, {("n", 1)}, osmscan.relations(path, {21}))
    assert (set(geometry.relations), set(geometry.ways), set(geometry.nodes)) == (
        {21},
        {11},
        {1, 2, 3},
    )


# ------------------------------------------------------- relations_where ---
def test_relations_where_are_those_whose_tags_the_predicate_picks(tmp_path: Path) -> None:
    waterways = osmscan.relations_where(extract(tmp_path), lambda tags: "type" in tags)
    assert waterways == {
        22: {
            "rings": {"outer": [11, 10, 12], "inner": []},
            "member_ways": [11, 10, 12],
            "label": None,
            "tags": {"type": "waterway"},
        }
    }


# ----------------------------------------------------------------- across ---
HELD = {"sh.osm.pbf": {("n", 1): "Naibel"}, "dk.osm.pbf": {("n", 1): "again", ("n", 2): "Fanø"}}


class Reads:
    """A stand-in for a read of one extract, which notes what it was asked for."""

    def __init__(self) -> None:
        self.asked: dict[str, set[OsmRef]] = {}

    def __call__(self, pbf: StrPath, refs: set[OsmRef]) -> dict[OsmRef, str]:
        self.asked[str(pbf)] = refs
        return {ref: name for ref, name in HELD[str(pbf)].items() if ref in refs}


def test_what_several_extracts_hold_is_found_in_the_first_that_holds_it() -> None:
    found = osmscan.across(["sh.osm.pbf", "dk.osm.pbf"], {("n", 1), ("n", 2), ("n", 3)}, Reads())
    assert found == {("n", 1): "Naibel", ("n", 2): "Fanø"}


def test_a_later_extract_is_asked_only_for_what_the_earlier_ones_lacked() -> None:
    read = Reads()
    osmscan.across(["sh.osm.pbf", "dk.osm.pbf"], {("n", 1), ("n", 2), ("n", 3)}, read)
    assert read.asked["dk.osm.pbf"] == {("n", 2), ("n", 3)}
