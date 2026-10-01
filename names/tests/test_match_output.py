"""match.py's worklist -- work/matches.csv and REPORT.md -- names a row by its
id, which stays put when rows are added above it (#23); a dry run changes no
tracked file, and REPORT.md depends on the inputs alone (#24)."""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

import pytest

from frasch import match
from conftest import cand, places_text, write_candidates

TOFTUM = cand("n", 240044107, 8.83, 54.71, place="village", name="Toftum")
UPHUSUM = [cand("n", 1, 8.90, 54.70, place="hamlet", name="Uphusum"),
           cand("n", 2, 8.95, 54.75, place="hamlet", name="Uphusum")]
ROWS = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    {"id": "aphusem-2", "kind": "settlement", "mooring": "Aphüsem", "de": "Uphusum"},
]


def write_inputs(world: Path) -> None:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)


def match_main(world: Path, *extra: str) -> None:
    code = match.main(["--names", str(world / "places.csv"),
                       "--candidates", str(world / "work" / "candidates.jsonl"),
                       "--matches", str(world / "work" / "matches.csv"),
                       "--report", str(world / "REPORT.md"), "--offline",
                       "--wikidata-cache", str(world / "work" / "wd.json"), *extra])
    assert code == 0


def run_match(world: Path) -> None:
    write_inputs(world)
    match_main(world)


def test_matches_csv_keys_each_row_by_its_id(world: Path) -> None:
    run_match(world)
    with open(world / "work" / "matches.csv", encoding="utf-8", newline="") as fh:
        got = [(m["id"], m["line"], m["result"]) for m in csv.DictReader(fh)]
    assert got == [("toftem", "2", "matched"), ("aphusem-2", "3", "ambiguous")]


def test_the_report_names_a_row_by_id_and_line(world: Path) -> None:
    run_match(world)
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert "| aphusem-2 | 3 | settlement | Aphüsem | Uphusum |" in report


def tracked_hashes(world: Path) -> dict[str, str]:
    """sha256 of every file of the world outside the git-ignored work/."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in world.iterdir() if p.is_file()}


def test_a_dry_run_changes_no_tracked_file(world: Path) -> None:
    write_inputs(world)
    (world / "REPORT.md").write_text("# an older report\n", encoding="utf-8")
    before = tracked_hashes(world)
    match_main(world, "--dry-run")
    assert tracked_hashes(world) == before
    assert sorted(before) == ["REPORT.md", "curation.csv", "places.csv"]


def test_the_report_carries_no_date_or_run_time(world: Path) -> None:
    # a real run on unchanged inputs must leave the tracked REPORT.md as it was
    run_match(world)
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert not re.search(r"\d{4}-\d\d-\d\d|\d+s\b", report)


def test_an_ok_row_without_a_reference_is_left_alone_and_counted_by_hand(world: Path) -> None:
    rows = ROWS + [{"id": "aphusem-3", "kind": "settlement", "mooring": "Aphüsem",
                    "de": "Uphusum", "status": "ok"}]
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)
    match_main(world)
    with open(world / "places.csv", encoding="utf-8", newline="") as fh:
        checked = [r for r in csv.DictReader(fh) if r["id"] == "aphusem-3"]
    assert [(r["osm"], r["status"]) for r in checked] == [("", "ok")]
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert "| **total** | **1** | **1** | **0** | **1** | **0** |" in report
    assert "| aphusem-3 |" not in report.split("## Not found")[1]
    with open(world / "work" / "matches.csv", encoding="utf-8", newline="") as fh:
        assert [m["result"] for m in csv.DictReader(fh) if m["id"] == "aphusem-3"] \
            == ["by hand"]


def test_a_run_that_cannot_write_matches_csv_leaves_places_csv_alone(world: Path) -> None:
    # matches.csv goes first: places.csv and the worklist never disagree
    write_inputs(world)
    (world / "work" / "matches.csv").mkdir()            # cannot be replaced
    before = (world / "places.csv").read_bytes()
    with pytest.raises(OSError):
        match_main(world)
    assert (world / "places.csv").read_bytes() == before
