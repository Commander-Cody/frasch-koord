"""The matcher's worklist -- work/matches.csv and REPORT.md -- names a row by its
id, which stays put when rows are added above it (#23); a dry run changes no
tracked file, and REPORT.md depends on the inputs alone (#24)."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

import pytest

from frasch import match, placelist
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
    with open(world / "work" / "matches.csv", encoding="utf-8", newline="") as fh:
        assert [m["result"] for m in csv.DictReader(fh) if m["id"] == "aphusem-3"] == ["by hand"]


def test_a_run_that_cannot_write_matches_csv_leaves_places_csv_alone(world: Path) -> None:
    # matches.csv goes first: places.csv and the worklist never disagree
    write_inputs(world)
    (world / "work" / "matches.csv").mkdir()  # cannot be replaced
    before = (world / "places.csv").read_bytes()
    with pytest.raises(OSError):
        match_main(world)
    assert (world / "places.csv").read_bytes() == before


# one row in every state of the report, and two rows sharing one object
EVERY_STATE = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"}
    | {"osm": "node/240044107", "status": "auto"},
    {"id": "hulm", "kind": "settlement", "mooring": "Hulm", "de": "Holm", "osm": "node/240102263"},
    {"id": "aphusem", "kind": "settlement", "mooring": "Aphüsem", "de": "Uphusum", "status": "ok"},
    {"id": "westerhiis", "kind": "settlement", "mooring": "Wäästerhiis", "de": "Westerheide"}
    | {"osm": "local/westerheide-amrum"},
    {"id": "schoerkewaerw", "kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft"}
    | {"hint": "Hooge"},
    {"id": "kaamp", "kind": "settlement", "solring": "Kaamp", "de": "Kampen"},
    {"id": "wiringhiird", "kind": "landscape", "mooring": "Wiringhiird", "da": "Vidingherred"},
    {"id": "hoorst", "kind": "settlement", "mooring": "Hoorst", "status": "skip"},
    {"id": "morsum", "kind": "settlement", "de": "Morsum"},
    {"id": "halie", "kind": "not_a_place", "mooring": "Halie"},
    {"id": "hulm-2", "kind": "settlement", "mooring": "Holm", "de": "Holm"}
    | {"osm": "node/240102263", "status": "ok"},
]
# 22 near misses: the report keeps the first 20 whole ones
KAMPEN_STREETS = ";".join(f"w/{i}:Kampen:residential:150" for i in range(1000001, 1000023))
KAMPEN_STREETS_SHOWN = ";".join(f"w/{i}:Kampen:residential:150" for i in range(1000001, 1000021))
EVERY_STATE_RESULTS = {
    "schoerkewaerw": {
        "status": "ambiguous",
        "note": "location hint 'Hooge' matched no cluster",
        "candidates": "n/11711096159:Kirchwarft:hamlet:21;n/1333738478:Kirchwarft:hamlet:5",
    },
    "kaamp": {
        "status": "not_found",
        "note": "22 name match(es), none compatible with kind=settlement",
        "candidates": KAMPEN_STREETS,
    },
}
EVERY_STATE_REPORT = (
    """\
# Name matching report

Generated by `frasch match` from `names/places.csv` (11 rows). `id` is the row's `id` cell, \
`line` its line number in that file.

Hand-review worklist: for every **ambiguous** row below pick the right object and write it into \
the `osm` column of `names/places.csv` (`node/123`, `way/123`, `relation/123`); for the \
**not found** rows look the feature up on openstreetmap.org yourself. Put `ok` in `status` when \
you have checked a row (or leave it empty), `skip` when the row must never be put on the map. \
`frasch match` only ever rewrites rows with `status=auto` or with empty `osm`/`wikidata`/`status` \
cells. **own point** rows carry a local reference (`local/<slug>`, a place OSM does not have, \
positioned in `names/curation.csv`) and are never touched.

## Counts

| kind | auto | by hand | own point | ambiguous | not found | skip | no Frisian name | not a place \
| total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| settlement | 1 | 3 | 1 | 0 | 1 | 1 | 1 | 0 | 8 |
| warft | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| landscape | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| not_a_place | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| **total** | **1** | **3** | **1** | **1** | **2** | **1** | **1** | **1** | **11** |

## Ambiguous (1)

`candidates` format: `type/id:name:class:km-from-NF-centre`

| id | line | kind | Frisian | German | hint | why | candidates |
|---|---:|---|---|---|---|---|---|
| schoerkewaerw | 6 | warft | Schörkewärw | Kirchwarft | Hooge \
| location hint 'Hooge' matched no cluster \
| `n/11711096159:Kirchwarft:hamlet:21;n/1333738478:Kirchwarft:hamlet:5` |

## Rows sharing one OSM object (1)

The list has these places twice (two spellings, or rows from two sheet sections). Only one name \
can be injected -- the first row wins; decide which, and `skip` the other.

| OSM object | rows (line) | Frisian names | German |
|---|---|---|---|
| `node/240102263` | hulm (3), hulm-2 (12) | Hulm, Holm | Holm |

## Not found (2)

Either the feature is not in OSM at all, or OSM spells it differently. `near misses` lists \
objects that do carry the German name but are the wrong kind of thing (a street, a bus stop, a \
building) -- occasionally one of them is still the right answer.

| id | line | kind | Frisian | German | note | near misses |
|---|---:|---|---|---|---|---|
| kaamp | 7 | settlement | Kaamp | Kampen | 22 name match(es), none compatible with \
kind=settlement | `"""
    + KAMPEN_STREETS_SHOWN
    + """;... (+2 more)` |
| wiringhiird | 8 | landscape | Wiringhiird | Vidingherred |  |  |
"""
)


def test_the_report_has_a_section_for_every_state(world: Path) -> None:
    (world / "places.csv").write_text(places_text(EVERY_STATE), encoding="utf-8")
    rows, _fields = placelist.read(str(world / "places.csv"), REGISTRY)
    match.write_report(rows, EVERY_STATE_RESULTS, str(world / "REPORT.md"), REGISTRY)
    assert (world / "REPORT.md").read_text(encoding="utf-8") == EVERY_STATE_REPORT


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
    paths = {"matches": world / "work" / "matches.csv", "report": world / "REPORT.md"}
    assert wrote_line.format(**paths) in out


def test_a_run_writes_the_new_references_into_places_csv(world: Path) -> None:
    (world / "places.csv").write_text(places_text(REMATCHED), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM, HOLM)
    match_main(world)
    rows, _fields = placelist.read(str(world / "places.csv"), REGISTRY)
    assert [(r["id"], r["osm"], r["wikidata"], r["status"]) for r in rows] == [
        ("toftem", "node/240044107", "", "auto"),
        ("aphusem", "", "", ""),
        ("hulm", "node/240102263", "Q559369", "auto"),
    ]


def test_the_command_matches_the_workspace_its_options_name(world: Path) -> None:
    write_inputs(world)
    files = path_options(workspace(world), "names", "dialects", "report", "work")
    assert main(["match", *files, "--offline", "--dry-run"]) == 0
    assert (world / "work" / "matches.csv").exists()
    assert not (world / "REPORT.md").exists()
