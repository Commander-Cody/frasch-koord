"""match.py and the extracts behind candidates.jsonl (#24): its readers skip
the header, and a run warns when the set of extracts changed since the last
one -- dropping the Denmark extract clears every `auto` row only it has."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import curate
from frasch import match
from frasch import placelist
from frasch.nameindex import NameIndex
from frasch.candidates import HeaderLine, read_records
from frasch.provenance import ExtractStamp
from conftest import REGISTRY, cand, places_text, workspace, write_candidates

SH: ExtractStamp = {
    "file": "schleswig-holstein-latest.osm.pbf",
    "replication_timestamp": "2026-09-20T20:21:02Z",
}
DK: ExtractStamp = {
    "file": "denmark-latest.osm.pbf",
    "replication_timestamp": "2026-09-21T20:20:00Z",
}
HEADER: HeaderLine = {"header": {"extracts": [SH]}}
TOFTUM = cand("n", 240044107, 8.83, 54.71, place="village", name="Toftum")
HOYER = cand(
    "n",
    26854466,
    8.693,
    54.9602,
    src="denmark",
    place="town",
    name="Højer",
    name__de="Hoyer",
    name__da="Højer",
)
ROWS = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    {"id": "huuger", "kind": "settlement", "mooring": "Huuger", "de": "Hoyer"},
]


def test_the_index_skips_the_header(tmp_path: Path) -> None:
    index = NameIndex(read_records(str(write_candidates(tmp_path / "c.jsonl", HEADER, TOFTUM))))
    assert [r["id"] for r in index.recs] == [240044107]


def test_the_curation_export_skips_the_header(tmp_path: Path) -> None:
    path = write_candidates(tmp_path / "c.jsonl", HEADER, TOFTUM)
    kept = curate.stream_records(str(path), {("n", 240044107)}, set())
    assert [r["id"] for r in kept] == [240044107]


# ------------------------------------------------------------ extract set ---
def run_match(world: Path, extracts: list[ExtractStamp] | None, dry_run: bool = False) -> None:
    """The matcher on ROWS against candidates built from `extracts` (None: a file
    from before the header); the extracts of HOYER's are DK's only."""
    recs = [TOFTUM] + ([HOYER] if extracts and DK["file"] in {e["file"] for e in extracts} else [])
    header: list[HeaderLine] = [{"header": {"extracts": extracts}}] if extracts is not None else []
    write_candidates(world / "work" / "candidates.jsonl", *header, *recs)
    places = world / "places.csv"
    if not places.exists():
        places.write_text(places_text(ROWS), encoding="utf-8")
    assert match.run(workspace(world), REGISTRY, offline=True, dry_run=dry_run) == 0


def recorded(world: Path) -> object:
    path = world / "work" / "match-extracts.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def statuses(world: Path) -> dict[str, str]:
    rows, _ = placelist.read(str(world / "places.csv"), REGISTRY)
    return {r["id"]: r["status"] for r in rows}


def test_a_run_records_the_extracts_it_used(world: Path) -> None:
    run_match(world, [SH, DK])
    assert recorded(world) == {"extracts": [SH, DK]}


def test_a_dry_run_records_nothing(world: Path) -> None:
    run_match(world, [SH, DK], dry_run=True)
    assert recorded(world) is None


def test_a_dropped_extract_is_named_and_its_rows_said_to_be_cleared(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_match(world, [SH, DK])
    assert statuses(world) == {"toftem": "auto", "huuger": "auto"}
    capsys.readouterr()
    run_match(world, [SH])
    err = capsys.readouterr().err
    assert "dropped: denmark-latest.osm.pbf" in err
    assert "cleared" in err
    assert statuses(world) == {"toftem": "auto", "huuger": ""}
    assert recorded(world) == {"extracts": [SH]}


def test_an_added_extract_is_named(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_match(world, [SH])
    capsys.readouterr()
    run_match(world, [SH, DK], dry_run=True)
    assert "added: denmark-latest.osm.pbf" in capsys.readouterr().err


def test_a_refreshed_extract_is_no_warning(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_match(world, [SH, DK])
    capsys.readouterr()
    run_match(world, [{**SH, "replication_timestamp": "2026-09-27T20:21:02Z"}, DK])
    assert capsys.readouterr().err == ""


def test_candidates_without_a_header_are_to_be_rebuilt(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_match(world, None)
    assert "rebuild it with `just candidates`" in capsys.readouterr().err
    assert recorded(world) is None
