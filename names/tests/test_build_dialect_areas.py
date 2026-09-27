"""build_dialect_areas.assemble_rings: a boundary relation's member ways, in
whatever order and direction OSM keeps them, joined into closed rings.  The
dialect areas and the injector's point-in-own-polygon lookup both rest on
it.  Node ids stand in for the nodes; a ring is closed when it ends on the
node it started with."""
from __future__ import annotations

import build_dialect_areas as bda


def same_ring(a, b):
    """Two closed rings around the same nodes, whatever node they start at
    and whichever way round they run."""
    if a[0] != a[-1] or b[0] != b[-1] or len(a) != len(b):
        return False
    a, b = a[:-1], b[:-1]
    turns = [b[i:] + b[:i] for i in range(len(b))]
    return a in turns or a[::-1] in turns


def test_a_closed_way_is_a_ring_by_itself():
    assert bda.assemble_rings([[1, 2, 3, 1]]) == ([[1, 2, 3, 1]], [])


def test_ways_meeting_end_to_start_are_joined():
    assert bda.assemble_rings([[1, 2, 3], [3, 4, 1]]) == ([[1, 2, 3, 4, 1]], [])


def test_a_way_running_the_other_way_is_reversed_to_fit():
    assert bda.assemble_rings([[1, 2, 3], [1, 4, 3]]) == ([[1, 2, 3, 4, 1]], [])


def test_a_way_ending_where_the_ring_starts_goes_in_front():
    assert bda.assemble_rings([[2, 3, 4], [1, 2], [4, 5, 1]]) == ([[1, 2, 3, 4, 5, 1]], [])


def test_a_way_starting_where_the_ring_starts_is_reversed_in_front():
    assert bda.assemble_rings([[2, 3, 4], [2, 1], [4, 5, 1]]) == ([[1, 2, 3, 4, 5, 1]], [])


def test_member_order_does_not_matter():
    # the ways of one ring, shuffled and partly reversed
    (ring,), unclosed = bda.assemble_rings([[4, 1], [2, 3], [4, 3], [1, 2]])
    assert same_ring(ring, [1, 2, 3, 4, 1])
    assert unclosed == []


def test_separate_islands_are_separate_rings():
    rings, unclosed = bda.assemble_rings([[1, 2, 3], [10, 11, 12, 10], [3, 4, 1]])
    assert rings == [[1, 2, 3, 4, 1], [10, 11, 12, 10]]
    assert unclosed == []


def test_a_gap_leaves_the_chain_unclosed():
    # a member way missing from the extract
    assert bda.assemble_rings([[1, 2, 3], [3, 4, 5]]) == ([], [[1, 2, 3, 4, 5]])


def test_ways_with_fewer_than_two_nodes_are_ignored():
    assert bda.assemble_rings([[7], [], [1, 2, 3, 1]]) == ([[1, 2, 3, 1]], [])


def test_a_ring_needs_three_corners():
    # there and back along one edge closes, but encloses nothing
    assert bda.assemble_rings([[1, 2], [2, 1]]) == ([], [[1, 2, 1]])


def test_the_input_ways_are_not_modified():
    ways = [[1, 2, 3], [3, 4, 1]]
    bda.assemble_rings(ways)
    assert ways == [[1, 2, 3], [3, 4, 1]]
