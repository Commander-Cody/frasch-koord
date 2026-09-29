"""build_candidates.py: the way-position store, and candidates.jsonl -- its
header naming the extracts it was built from, and the one-step write (#24)."""
from __future__ import annotations

from pathlib import Path

import osmium
import pytest

from frasch import build_candidates
from frasch import candidates
from frasch.build_candidates import WayCentroids
from conftest import cand, write_candidates
from osm_fixture import write_extract


# ------------------------------------------------------------ WayCentroids ---
def test_way_centroids_finds_a_way_by_id() -> None:
    ways = WayCentroids()
    ways.add(10, 8.5, 54.5)
    ways.add(20, 8.75, 54.75)
    assert ways.get(20) == (8.75, 54.75)
    assert ways.get(15) is None


def test_way_centroids_refuses_ways_out_of_order() -> None:
    # an unsorted extract used to make every later lookup return None, so
    # every relation silently lost its position
    ways = WayCentroids()
    ways.add(20, 8.75, 54.75)
    with pytest.raises(ValueError, match="osmium sort"):
        ways.add(10, 8.5, 54.5)


# ------------------------------------------------------- candidates.jsonl ---
TOFTUM = ((8.83, 54.71), {"name": "Toftum", "place": "village"})
HOYER = ((8.69, 54.96), {"name": "Højer", "name:de": "Hoyer", "place": "town"})


def extracts(tmp_path: Path) -> tuple[Path, Path]:
    """A Schleswig-Holstein and a Denmark extract, one village each."""
    sh = write_extract(tmp_path / "schleswig-holstein-latest.osm.pbf",
                       nodes={1: TOFTUM}, timestamp="2026-09-20T20:21:02Z")
    dk = write_extract(tmp_path / "denmark-latest.osm.pbf",
                       nodes={2: HOYER}, timestamp="2026-09-21T20:20:00Z")
    return sh, dk


def build(tmp_path: Path, *pbfs: Path) -> Path:
    out = tmp_path / "work" / "candidates.jsonl"
    assert build_candidates.main([*map(str, pbfs), "--out", str(out)]) == 0
    return out


def test_header_names_every_extract_with_its_timestamp(tmp_path: Path) -> None:
    out = build(tmp_path, *extracts(tmp_path))
    assert candidates.read_header(out) == [
        {"file": "schleswig-holstein-latest.osm.pbf",
         "replication_timestamp": "2026-09-20T20:21:02Z"},
        {"file": "denmark-latest.osm.pbf",
         "replication_timestamp": "2026-09-21T20:20:00Z"},
    ]


def test_records_follow_the_header(tmp_path: Path) -> None:
    out = build(tmp_path, *extracts(tmp_path))
    got = [(r["src"], r["t"], r["id"], r["tags"]["name"])
           for r in candidates.read_records(out)]
    assert got == [("schleswig-holstein", "n", 1, "Toftum"),
                   ("denmark", "n", 2, "Højer")]


def test_a_file_from_before_the_header_has_none_and_all_records(tmp_path: Path) -> None:
    legacy = write_candidates(tmp_path / "candidates.jsonl",
                              cand("n", 1, 8.83, 54.71, name="Toftum", place="village"))
    assert candidates.read_header(legacy) is None
    assert [r["id"] for r in candidates.read_records(legacy)] == [1]


def write_unsorted_extract(path: Path) -> Path:
    """Two named ways in descending id order -- what `osmium sort` fixes."""
    Node, Way = osmium.osm.mutable.Node, osmium.osm.mutable.Way
    w = osmium.SimpleWriter(str(path), overwrite=True)
    try:
        for i, loc in ((1, (8.8, 54.7)), (2, (8.9, 54.8))):
            w.add_node(Node(id=i, version=1, visible=True, location=loc))
        for i in (20, 10):
            w.add_way(Way(id=i, version=1, visible=True, nodes=[1, 2],
                          tags={"name": f"Weg {i}", "highway": "residential"}))
    finally:
        w.close()
    return path


def test_a_failed_build_leaves_the_old_file_and_no_temp_file(tmp_path: Path) -> None:
    sh, _dk = extracts(tmp_path)
    old = build(tmp_path, sh)
    before = old.read_bytes()
    unsorted = write_unsorted_extract(tmp_path / "unsorted.osm.pbf")
    with pytest.raises(ValueError, match="osmium sort"):
        build_candidates.main([str(sh), str(unsorted), "--out", str(old)])
    assert old.read_bytes() == before
    assert [p.name for p in old.parent.iterdir()] == ["candidates.jsonl"]
