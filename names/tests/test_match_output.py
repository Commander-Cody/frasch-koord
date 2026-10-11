"""What a run of the matcher writes -- work/matches.jsonl, REPORT.md and
places.csv.  The first two name a row by its id, which stays put when rows
are added above it (#23); a dry run changes no tracked file, and REPORT.md
depends on the inputs alone (#24)."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

import pytest

from frasch import match, matchfile, placelist
from frasch.__main__ import main
from conftest import REGISTRY, cand, path_options, places_text, workspace, write_candidates

TOFTUM = cand("n", 240044107, 8.83, 54.71, place="village", name="Toftum")
UPHUSUM = [
    cand("n", 1, 8.90, 54.70, place="hamlet", name="Uphusum"),
    cand("n", 2, 8.95, 54.75, place="hamlet", name="Uphusum"),
]
ROWS = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    {"id": "aphusem-2", "kind": "settlement", "mooring": "Aphüsem", "de": "Uphusum"},
]


def write_inputs(world: Path) -> None:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)


def match_main(world: Path, dry_run: bool = False) -> None:
    assert match.run(workspace(world), REGISTRY, offline=True, dry_run=dry_run) == 0


def run_match(world: Path) -> None:
    write_inputs(world)
    match_main(world)


def matches(world: Path) -> dict[str, matchfile.Entry]:
    """The matches file of the last run, by row id."""
    return {m["id"]: m for m in matchfile.read(world / "work" / "matches.jsonl")}


def test_the_matches_file_keys_each_row_by_its_id(world: Path) -> None:
    run_match(world)
    got = [(m["id"], m["result"]) for m in matchfile.read(world / "work" / "matches.jsonl")]
    assert got == [("toftem", "matched"), ("aphusem-2", "ambiguous")]


def test_a_dry_run_shows_the_reference_a_row_would_get(world: Path) -> None:
    write_inputs(world)
    match_main(world, dry_run=True)
    assert matches(world)["toftem"]["osm"] == "node/240044107"


def test_the_matches_file_says_where_the_hint_of_a_row_without_a_match_points(
    world: Path,
) -> None:
    lost = {"id": "ferlaasen", "kind": "settlement", "mooring": "Ferlääsen", "de": "Verloren"}
    rows = ROWS + [lost | {"hint": "Toftum"}]
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)
    match_main(world)
    # a village-sized circle around Toftum
    assert matches(world)["ferlaasen"]["hint_point"] == [8.83, 54.71, 8.0]


def test_the_matches_file_leaves_out_a_row_the_matcher_does_not_own(world: Path) -> None:
    checked = {"id": "aphusem-3", "kind": "settlement", "mooring": "Aphüsem", "status": "ok"}
    (world / "places.csv").write_text(places_text(ROWS + [checked]), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)
    match_main(world)
    assert sorted(matches(world)) == ["aphusem-2", "toftem"]


def test_the_report_names_a_row_by_id_and_line(world: Path) -> None:
    run_match(world)
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert "| aphusem-2 | 3 | settlement | Aphüsem | Uphusum |" in report


def tracked_hashes(world: Path) -> dict[str, str]:
    """sha256 of every file of the world outside the git-ignored work/."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in world.iterdir() if p.is_file()
    }


def test_a_dry_run_changes_no_tracked_file(world: Path) -> None:
    write_inputs(world)
    (world / "REPORT.md").write_text("# an older report\n", encoding="utf-8")
    before = tracked_hashes(world)
    match_main(world, dry_run=True)
    assert tracked_hashes(world) == before
    assert sorted(before) == [
        "REPORT.md",
        "curation.csv",
        "dialect_areas.csv",
        "dialects.csv",
        "places.csv",
    ]


def test_the_report_carries_no_date_or_run_time(world: Path) -> None:
    # a real run on unchanged inputs must leave the tracked REPORT.md as it was
    run_match(world)
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert not re.search(r"\d{4}-\d\d-\d\d|\d+s\b", report)


def test_an_ok_row_without_a_reference_is_left_alone_and_counted_by_hand(world: Path) -> None:
    rows = ROWS + [
        {
            "id": "aphusem-3",
            "kind": "settlement",
            "mooring": "Aphüsem",
            "de": "Uphusum",
            "status": "ok",
        }
    ]
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)
    match_main(world)
    with open(world / "places.csv", encoding="utf-8", newline="") as fh:
        checked = [r for r in csv.DictReader(fh) if r["id"] == "aphusem-3"]
    assert [(r["osm"], r["status"]) for r in checked] == [("", "ok")]
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert "| **total** | **1** | **1** | **0** | **1** | **0** |" in report
    assert "| aphusem-3 |" not in report.split("## Not found")[1]


def test_a_run_that_cannot_write_the_matches_file_leaves_places_csv_alone(world: Path) -> None:
    # the matches file goes first: places.csv and the worklist never disagree
    write_inputs(world)
    (world / "work" / "matches.jsonl").mkdir()  # cannot be replaced
    before = (world / "places.csv").read_bytes()
    with pytest.raises(OSError):
        match_main(world)
    assert (world / "places.csv").read_bytes() == before


HOLM = cand("n", 240102263, 8.866668, 54.833305, place="village", name="Holm", wikidata="Q559369")
# a row the matcher fills, one it clears and one it gives another object
REMATCHED = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    {"id": "aphusem", "kind": "settlement", "mooring": "Aphüsem", "de": "Uphusum"}
    | {"osm": "node/1", "status": "auto"},
    {"id": "hulm", "kind": "settlement", "mooring": "Hulm", "de": "Holm"}
    | {"osm": "node/7", "wikidata": "Q1", "status": "auto"},
]


@pytest.mark.parametrize(
    "dry_run,places_line,wrote_line",
    [
        (False, "places.csv: 1 rows filled, 1 cleared, 1 changed", "wrote {matches} and {report}"),
        (
            True,
            "places.csv: 1 rows filled, 1 cleared, 1 changed (dry run -- not written)",
            "wrote {matches}",
        ),
    ],
)
def test_a_run_counts_the_rows_it_filled_cleared_and_changed(
    world: Path,
    capsys: pytest.CaptureFixture[str],
    dry_run: bool,
    places_line: str,
    wrote_line: str,
) -> None:
    (world / "places.csv").write_text(places_text(REMATCHED), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM, HOLM)
    match_main(world, dry_run)
    out = capsys.readouterr().out.splitlines()
    assert "matcher owns 3 of 3 rows: 2 matched, 1 ambiguous" in out
    assert places_line in out
    paths = {"matches": world / "work" / "matches.jsonl", "report": world / "REPORT.md"}
    assert wrote_line.format(**paths) in out


def test_a_run_writes_the_new_references_into_places_csv(world: Path) -> None:
    (world / "places.csv").write_text(places_text(REMATCHED), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM, HOLM)
    match_main(world)
    rows = placelist.read(str(world / "places.csv"), REGISTRY).rows
    assert [(r["id"], r["osm"], r["wikidata"], r["status"]) for r in rows] == [
        ("toftem", "node/240044107", "", "auto"),
        ("aphusem", "", "", ""),
        ("hulm", "node/240102263", "Q559369", "auto"),
    ]


def test_the_command_matches_the_workspace_its_options_name(world: Path) -> None:
    write_inputs(world)
    files = path_options(workspace(world), "names", "dialects", "report", "work")
    assert main(["match", *files, "--offline", "--dry-run"]) == 0
    assert (world / "work" / "matches.jsonl").exists()
    assert not (world / "REPORT.md").exists()
