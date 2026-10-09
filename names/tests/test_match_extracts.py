"""match.py and the extracts behind candidates.jsonl (#24): its readers skip
the header, and a run warns when the set of extracts changed since the last
one -- dropping the Denmark extract clears every `auto` row only it has."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from frasch import curate
from frasch import match
from frasch import placelist
from frasch.errors import PipelineError
from frasch.nameindex import NameIndex
from frasch.candidates import read_records
from frasch.provenance import ExtractStamp, Stamp, blob_hash
from conftest import REGISTRY, cand, places_text, workspace, write_candidates

SH: ExtractStamp = {
    "file": "schleswig-holstein-latest.osm.pbf",
    "replication_timestamp": "2026-09-20T20:21:02Z",
}
DK: ExtractStamp = {
    "file": "denmark-latest.osm.pbf",
    "replication_timestamp": "2026-09-21T20:20:00Z",
}
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
    index = NameIndex(
        read_records(str(write_candidates(tmp_path / "c.jsonl", TOFTUM, extracts=[SH])))
    )
    assert [r["id"] for r in index.recs] == [240044107]


def test_the_curation_export_skips_the_header(tmp_path: Path) -> None:
    path = write_candidates(tmp_path / "c.jsonl", TOFTUM, extracts=[SH])
    kept = curate.stream_records(str(path), {("n", 240044107)}, set())
    assert [r["id"] for r in kept] == [240044107]


# ------------------------------------------------------------ extract set ---
def run_match(world: Path, extracts: list[ExtractStamp], dry_run: bool = False) -> None:
    """The matcher on ROWS against candidates built from `extracts`; the
    extracts of HOYER's are DK's only."""
    recs = [TOFTUM] + ([HOYER] if DK["file"] in {e["file"] for e in extracts} else [])
    write_candidates(world / "work" / "candidates.jsonl", *recs, extracts=extracts)
    places = world / "places.csv"
    if not places.exists():
        places.write_text(places_text(ROWS), encoding="utf-8")
    assert match.run(workspace(world), REGISTRY, offline=True, dry_run=dry_run) == 0


def recorded(world: Path) -> Sequence[ExtractStamp] | None:
    """The extracts the report says it was written from."""
    stamp = Stamp.read(world / "REPORT.md")
    return stamp.extracts if stamp else None


def statuses(world: Path) -> dict[str, str]:
    rows, _ = placelist.read(str(world / "places.csv"), REGISTRY)
    return {r["id"]: r["status"] for r in rows}


def test_the_report_is_stamped_with_the_extracts_behind_the_candidates(world: Path) -> None:
    run_match(world, [SH, DK])
    assert recorded(world) == [SH, DK]


def test_the_report_is_stamped_with_the_name_list_as_the_run_left_it(world: Path) -> None:
    run_match(world, [SH, DK])
    stamp = Stamp.read(world / "REPORT.md")
    assert stamp is not None and stamp.inputs == {
        "places.csv": blob_hash(world / "places.csv"),
        "dialects.csv": blob_hash(world / "dialects.csv"),
    }


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
    assert recorded(world) == [SH]


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


def test_candidates_that_name_no_extracts_stop_the_match(world: Path) -> None:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    candidates = world / "work" / "candidates.jsonl"
    # a record where the header belongs: nothing says which extracts it is from
    candidates.write_text(json.dumps(TOFTUM) + "\n", encoding="utf-8")
    with pytest.raises(PipelineError) as stop:
        match.run(workspace(world), REGISTRY, offline=True)
    assert str(stop.value) == (
        f"{candidates} does not say what it was built from -- "
        "build it with `just rebuild candidates`"
    )


def test_a_report_that_names_no_extracts_is_not_compared_with(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_match(world, [])
    capsys.readouterr()
    run_match(world, [SH, DK])
    assert capsys.readouterr().err == ""


def test_a_match_without_candidates_stops_with_how_to_scan_them(world: Path) -> None:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    with pytest.raises(
        PipelineError, match="candidates.jsonl not found -- build it with `just rebuild candidates`"
    ):
        match.run(workspace(world), REGISTRY, offline=True)
