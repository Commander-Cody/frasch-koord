"""osmgeom.py: an OSM object's ways and nodes, read out of an extract by
frasch.osmscan, become its polygon(s).  The dialect areas and the objects
file (a place's point inside its own polygon) both rest on it, so a place
and the areas it is compared against are read out of OSM the same way.

`assemble_rings`: a boundary relation's member ways, in whatever order and
direction OSM keeps them, joined into closed rings.  Node ids stand in for
the nodes; a ring is closed when it ends on the node it started with."""

from __future__ import annotations

import pytest

from frasch import osmgeom
from frasch.osmscan import Rings


def same_ring(a: list[int], b: list[int]) -> bool:
    """Two closed rings around the same nodes, whatever node they start at
    and whichever way round they run."""
    if a[0] != a[-1] or b[0] != b[-1] or len(a) != len(b):
        return False
    a, b = a[:-1], b[:-1]
    turns = [b[i:] + b[:i] for i in range(len(b))]
    return a in turns or a[::-1] in turns


def test_a_closed_way_is_a_ring_by_itself() -> None:
    assert osmgeom.assemble_rings([[1, 2, 3, 1]]) == ([[1, 2, 3, 1]], [])


def test_ways_meeting_end_to_start_are_joined() -> None:
    assert osmgeom.assemble_rings([[1, 2, 3], [3, 4, 1]]) == ([[1, 2, 3, 4, 1]], [])


def test_a_way_running_the_other_way_is_reversed_to_fit() -> None:
    assert osmgeom.assemble_rings([[1, 2, 3], [1, 4, 3]]) == ([[1, 2, 3, 4, 1]], [])


def test_a_way_ending_where_the_ring_starts_goes_in_front() -> None:
    assert osmgeom.assemble_rings([[2, 3, 4], [1, 2], [4, 5, 1]]) == ([[1, 2, 3, 4, 5, 1]], [])


def test_a_way_starting_where_the_ring_starts_is_reversed_in_front() -> None:
    assert osmgeom.assemble_rings([[2, 3, 4], [2, 1], [4, 5, 1]]) == ([[1, 2, 3, 4, 5, 1]], [])


def test_member_order_does_not_matter() -> None:
    # the ways of one ring, shuffled and partly reversed
    (ring,), unclosed = osmgeom.assemble_rings([[4, 1], [2, 3], [4, 3], [1, 2]])
    assert same_ring(ring, [1, 2, 3, 4, 1])
    assert unclosed == []


def test_separate_islands_are_separate_rings() -> None:
    rings, unclosed = osmgeom.assemble_rings([[1, 2, 3], [10, 11, 12, 10], [3, 4, 1]])
    assert rings == [[1, 2, 3, 4, 1], [10, 11, 12, 10]]
    assert unclosed == []


def test_a_gap_leaves_the_chain_unclosed() -> None:
    # a member way missing from the extract
    assert osmgeom.assemble_rings([[1, 2, 3], [3, 4, 5]]) == ([], [[1, 2, 3, 4, 5]])


def test_ways_with_fewer_than_two_nodes_are_ignored() -> None:
    assert osmgeom.assemble_rings([[7], [], [1, 2, 3, 1]]) == ([[1, 2, 3, 1]], [])


def test_a_ring_needs_three_corners() -> None:
    # there and back along one edge closes, but encloses nothing
    assert osmgeom.assemble_rings([[1, 2], [2, 1]]) == ([], [[1, 2, 1]])


def test_the_input_ways_are_not_modified() -> None:
    ways = [[1, 2, 3], [3, 4, 1]]
    osmgeom.assemble_rings(ways)
    assert ways == [[1, 2, 3], [3, 4, 1]]


# ----------------------------------------------------------- polygons_for ---
SQUARE = {
    1: (8.0, 54.0),
    2: (8.4, 54.0),
    3: (8.4, 54.4),
    4: (8.0, 54.4),
    5: (8.1, 54.1),
    6: (8.2, 54.1),
    7: (8.2, 54.2),
    8: (8.1, 54.2),
}


def test_a_closed_way_is_its_polygon() -> None:
    (poly,) = osmgeom.polygons_for(("w", 10), {}, {10: [1, 2, 3, 4, 1]}, SQUARE, [])
    assert poly.area == pytest.approx(0.16)


def test_a_relation_is_its_outer_rings_minus_its_inner_ones() -> None:
    rel: dict[int, Rings] = {20: {"outer": [10, 11], "inner": [12]}}
    ways = {10: [1, 2, 3], 11: [3, 4, 1], 12: [5, 6, 7, 8, 5]}
    (poly,) = osmgeom.polygons_for(("r", 20), rel, ways, SQUARE, [])
    assert poly.area == pytest.approx(0.16 - 0.01)


def test_a_member_way_the_extract_lacks_is_reported() -> None:
    problems: list[str] = []
    rel: dict[int, Rings] = {20: {"outer": [10, 11], "inner": []}}
    assert osmgeom.polygons_for(("r", 20), rel, {10: [1, 2, 3]}, SQUARE, problems) == []
    assert problems == [
        "relation/20: 1 outer way(s) not in the file",
        "relation/20: 1 unclosed outer ring(s) -- skipped",
    ]


def test_an_object_the_extract_lacks_has_no_polygon() -> None:
    assert osmgeom.polygons_for(("w", 10), {}, {}, SQUARE, []) == []
    assert osmgeom.polygons_for(("r", 20), {}, {}, SQUARE, []) == []
