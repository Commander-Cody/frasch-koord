"""build_candidates.py: the way-position store, and candidates.jsonl -- its
header naming the extracts it was built from, and the one-step write (#24)."""

from __future__ import annotations

import re
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
    sh = write_extract(
        tmp_path / "schleswig-holstein-latest.osm.pbf",
        nodes={1: TOFTUM},
        timestamp="2026-09-20T20:21:02Z",
    )
    dk = write_extract(
        tmp_path / "denmark-latest.osm.pbf", nodes={2: HOYER}, timestamp="2026-09-21T20:20:00Z"
    )
    return sh, dk


def build(tmp_path: Path, *pbfs: Path) -> Path:
    out = tmp_path / "work" / "candidates.jsonl"
    assert build_candidates.main([*map(str, pbfs), "--out", str(out)]) == 0
    return out


def test_header_names_every_extract_with_its_timestamp(tmp_path: Path) -> None:
    out = build(tmp_path, *extracts(tmp_path))
    assert candidates.read_header(out) == [
        {
            "file": "schleswig-holstein-latest.osm.pbf",
            "replication_timestamp": "2026-09-20T20:21:02Z",
        },
        {"file": "denmark-latest.osm.pbf", "replication_timestamp": "2026-09-21T20:20:00Z"},
    ]


def test_records_follow_the_header(tmp_path: Path) -> None:
    out = build(tmp_path, *extracts(tmp_path))
    got = [(r["src"], r["t"], r["id"], r["tags"]["name"]) for r in candidates.read_records(out)]
    assert got == [("schleswig-holstein", "n", 1, "Toftum"), ("denmark", "n", 2, "Højer")]


def test_a_file_from_before_the_header_has_none_and_all_records(tmp_path: Path) -> None:
    legacy = write_candidates(
        tmp_path / "candidates.jsonl", cand("n", 1, 8.83, 54.71, name="Toftum", place="village")
    )
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
            w.add_way(
                Way(
                    id=i,
                    version=1,
                    visible=True,
                    nodes=[1, 2],
                    tags={"name": f"Weg {i}", "highway": "residential"},
                )
            )
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


# ------------------------------------------------------- what is kept ---
def write_mixed_extract(path: Path) -> Path:
    """Named and unnamed nodes, ways and relations, some worth keeping."""
    return write_extract(
        path,
        nodes={
            1: ((8.83, 54.71), {"name": "Toftum", "place": "village", "population": "40"}),
            2: ((8.84, 54.72), {"name": "Kiosk", "shop": "kiosk"}),
            3: ((8.85, 54.73), {"place": "hamlet"}),
            4: ((8.86, 54.74), {"name:frr": "Hoorbel", "place": "hamlet"}),
            5: ((10.0, 54.3), {"name": "Kiel Hbf", "highway": "bus_stop"}),
            10: ((8.80, 54.60), {}),
            11: ((8.82, 54.60), {}),
            12: ((8.82, 54.62), {}),
            13: ((8.90, 54.70), {}),
            14: ((8.92, 54.72), {}),
        },
        ways={
            20: ([10, 11, 12], {"name": "Dorfstraße", "highway": "residential"}),
            21: ([13, 14], {}),
            22: ([12, 13], {"name": "Koogweg", "landuse": "farmland"}),
        },
        relations={
            30: (
                [("w", 21, "outer"), ("w", 22, "outer"), ("n", 1, "label")],
                {"name": "Neuer Koog", "place": "polder", "wikidata": "Q1"},
            ),
            31: ([("w", 99, "outer")], {"name": "Verloren", "boundary": "historic"}),
        },
    )


def test_main_keeps_named_classified_objects_with_their_positions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pbf = write_mixed_extract(tmp_path / "mixed.osm.pbf")
    out = build(tmp_path, pbf)

    # not kept: the kiosk (no class), the unnamed hamlet, the bus stop
    # (a road outside North Frisia) and the unnamed way; a relation's
    # position is the mean of its member ways' first nodes, or none at all
    assert list(candidates.read_records(out)) == [
        {
            "src": "mixed",
            "t": "n",
            "id": 1,
            "lon": 8.83,
            "lat": 54.71,
            "cls": ["place=village"],
            "tags": {"place": "village", "population": "40", "name": "Toftum"},
        },
        {
            "src": "mixed",
            "t": "n",
            "id": 4,
            "lon": 8.86,
            "lat": 54.74,
            "cls": ["place=hamlet"],
            "tags": {"place": "hamlet", "name:frr": "Hoorbel"},
        },
        {
            "src": "mixed",
            "t": "w",
            "id": 20,
            "lon": 8.813333,
            "lat": 54.606667,
            "cls": ["highway=residential"],
            "tags": {"highway": "residential", "name": "Dorfstraße"},
        },
        {
            "src": "mixed",
            "t": "w",
            "id": 22,
            "lon": 8.86,
            "lat": 54.66,
            "cls": ["landuse=farmland"],
            "tags": {"landuse": "farmland", "name": "Koogweg"},
        },
        {
            "src": "mixed",
            "t": "r",
            "id": 30,
            "lon": 8.86,
            "lat": 54.66,
            "cls": ["place=polder", "wikidata"],
            "tags": {"place": "polder", "wikidata": "Q1", "name": "Neuer Koog"},
        },
        {
            "src": "mixed",
            "t": "r",
            "id": 31,
            "lon": None,
            "lat": None,
            "cls": ["boundary=historic"],
            "tags": {"boundary": "historic", "name": "Verloren"},
        },
    ]
    stdout, stderr = (re.sub(r" \d+s$", " Ns", text, flags=re.M) for text in capsys.readouterr())
    assert (
        stderr == f"scanning {pbf} ...\n  mixed: 15 objects scanned, 3 way centroids cached, Ns\n"
    )
    assert stdout == (
        f"\nwrote 6 candidates to {out} in Ns\n"
        "  nodes 2  ways 2  relations 2\n"
        "counts by tag class (an object can count in several):\n"
        "         1  boundary\n"
        "         1  highway\n"
        "         1  landuse\n"
        "         3  place\n"
        "         1  wikidata\n"
    )
