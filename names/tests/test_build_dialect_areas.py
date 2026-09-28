"""build_dialect_areas.assemble_rings: a boundary relation's member ways, in
whatever order and direction OSM keeps them, joined into closed rings.  The
dialect areas and the injector's point-in-own-polygon lookup both rest on
it.  Node ids stand in for the nodes; a ring is closed when it ends on the
node it started with."""
from __future__ import annotations

import json

import pytest

from frasch import build_dialect_areas as bda, paths, registry
from frasch.errors import ValidationError
from frasch import dialects
from frasch import provenance
from osm_fixture import ring, write_extract


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


# ------------------------------------------------------------- read_areas ---
def test_an_osm_reference_on_two_rows_is_refused(tmp_path):
    # the review overlay's `?areas&area=` links name a row by its reference (#23)
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\n"
                     "frr-x-solring,relation/1147134,Sylt,\n"
                     "frr-x-solring,relation/1147133,Kampen,\n"
                     "frr-x-solring,relation/1147134,Sylt again,\n", encoding="utf-8")
    with pytest.raises(ValidationError, match=r"dialect_areas.csv:4: relation/1147134 "
                                         r"is already on line 2"):
        bda.read_areas(str(areas), registry.read())


# ------------------------------------------------------------------ main ---
# A tiny triangle way stands in for a whole municipality; `--registry` still
# points at the real dialects.csv so `frr-x-mooring` is a known tag.
def _write_fixture(tmp_path, csv_rows, timestamp=None):
    nodes, way = ring(1, (8.80, 54.55), (8.82, 54.55), (8.82, 54.57))
    pbf = write_extract(tmp_path / "extract.osm.pbf", nodes=nodes,
                        ways={1: (way, {})}, timestamp=timestamp)
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\n" + csv_rows, encoding="utf-8")
    return pbf, areas


def test_main_exits_nonzero_on_a_missing_reference_and_writes_nothing(tmp_path, capsys):
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n"
                                          "frr-x-mooring,way/999,Missing,\n")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"
    out.write_bytes(b"stale-out")
    parts_out.write_bytes(b"stale-parts")

    assert bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                     "--parts-out", str(parts_out), "--no-unassigned"]) == 1

    message = capsys.readouterr().err
    assert "way/999" in message
    assert "Missing" in message
    assert "frr-x-mooring" in message
    # nothing was written -- neither file changed
    assert out.read_bytes() == b"stale-out"
    assert parts_out.read_bytes() == b"stale-parts"


def test_allow_missing_writes_despite_a_missing_reference(tmp_path):
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n"
                                          "frr-x-mooring,way/999,Missing,\n")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                  "--parts-out", str(parts_out), "--no-unassigned",
                  "--allow-missing"])

    assert rc == 0
    assert out.exists()
    assert parts_out.exists()


def test_output_is_stamped_with_its_inputs(tmp_path):
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n",
                                timestamp="2026-09-22T20:22:59Z")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                  "--parts-out", str(parts_out), "--no-unassigned"])

    assert rc == 0
    expected = {
        "dialect_areas.csv": provenance.blob_hash(areas),
        "dialects.csv": provenance.blob_hash(paths.DIALECTS),
        "extracts": [{"file": "extract.osm.pbf",
                      "replication_timestamp": "2026-09-22T20:22:59Z"}],
    }
    fc = json.loads(out.read_text())
    assert fc["properties"]["built_from"] == expected
    parts_fc = json.loads(parts_out.read_text())
    assert parts_fc["properties"]["built_from"] == expected
    # AreaIndex.from_geojson must keep working with the stamped file
    idx = dialects.AreaIndex.from_geojson(str(out))
    assert len(idx) == 1

