"""osmscan.py: the id-filtered passes over an extract -- only the objects
asked for, never a location cache for the whole file."""

from __future__ import annotations

from pathlib import Path

from frasch import osmscan
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
            },
        )
    )


def test_relations_come_with_their_rings_label_and_tags(tmp_path: Path) -> None:
    assert osmscan.relations(extract(tmp_path), {20}) == {
        20: {
            "rings": {"outer": [10], "inner": [11]},
            "label": 4,
            "tags": {"boundary": "administrative"},
        }
    }


def test_a_member_without_a_role_is_an_outer_ring(tmp_path: Path) -> None:
    assert osmscan.relations(extract(tmp_path), {21})[21]["rings"] == {"outer": [11], "inner": []}


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
