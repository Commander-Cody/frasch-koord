"""matchreport.py: REPORT.md, the matcher's hand-review worklist, rendered
from the name list and the results of a run."""

from __future__ import annotations

import os
from pathlib import Path

from frasch import matchreport, placelist
from frasch.matchresult import MatchResult, Outcome, RankedCandidate
from frasch.provenance import Stamp
from conftest import REGISTRY, cand, places_text


def ranked(t: str, id: int, lon: float, lat: float, **tags: str) -> RankedCandidate:
    return {**cand(t, id, lon, lat, **tags), "rank": 0, "byname": False}


# one row in every state of the report
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
]
# 22 near misses, 150 km north of the centre of North Frisia (8.9, 54.7): the
# report keeps the first 20 whole ones
KAMPEN_STREETS = tuple(
    ranked("w", i, 8.9, 56.049, name="Kampen", highway="residential")
    for i in range(1000001, 1000023)
)
KAMPEN_STREETS_SHOWN = ";".join(f"w/{i}:Kampen:residential:150" for i in range(1000001, 1000021))
EVERY_STATE_RESULTS = {
    "schoerkewaerw": MatchResult(
        Outcome.AMBIGUOUS,
        "location hint 'Hooge' matched no cluster",
        candidates=(
            # 14 km south and 23 km west of the centre
            ranked("n", 11711096159, 8.544362, 54.572982, name="Kirchwarft", place="hamlet"),
            # 4 km south and 5 km west of it
            ranked("n", 1333738478, 8.826992, 54.664965, name="Kirchwarft", place="hamlet"),
        ),
    ),
    "kaamp": MatchResult(
        Outcome.NOT_FOUND,
        "22 name match(es), none compatible with kind=settlement",
        candidates=KAMPEN_STREETS,
    ),
}
STAMP = Stamp({"places.csv": "ce013625030ba8dba906f756967f9e9ca394464a"}, [])


def report_of(world: Path, rows: list[dict[str, str]], results: dict[str, MatchResult]) -> str:
    """The report of the name list `rows`, as a run with `results` writes it."""
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    listed = placelist.read(str(world / "places.csv"), REGISTRY).rows
    matchreport.write(listed, results, str(world / "REPORT.md"), REGISTRY, STAMP)
    return (world / "REPORT.md").read_text(encoding="utf-8")


def report_lines(
    world: Path, rows: list[dict[str, str]], results: dict[str, MatchResult]
) -> list[str]:
    """The lines of `report_of` the name list `rows`."""
    return report_of(world, rows, results).split("\n")


KAAMP = {"id": "kaamp", "kind": "settlement", "solring": "Kaamp", "de": "Kampen"}


def with_candidate(world: Path, candidate: RankedCandidate) -> str:
    """The report of a list whose one row is ambiguous, with `candidate`."""
    results = {"kaamp": MatchResult(Outcome.AMBIGUOUS, candidates=(candidate,))}
    return report_of(world, [KAAMP], results)


# ------------------------------------------------------------- the counts ---
def test_the_report_says_how_many_rows_it_was_generated_from(world: Path) -> None:
    assert "from `names/places.csv` (10 rows)." in report_of(world, EVERY_STATE, {})


def test_the_counts_have_a_column_per_state_in_order(world: Path) -> None:
    assert (
        "| kind | auto | by hand | own point | ambiguous | not found | skip | no Frisian name "
        "| not a place | total |"
    ) in report_lines(world, [KAAMP], {})


def test_the_counts_have_a_line_per_kind_in_the_order_the_kinds_first_appear(
    world: Path,
) -> None:
    warft = {"kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft"}
    rows = [warft | {"id": "a"}, KAAMP, warft | {"id": "b"}]

    lines = report_lines(world, rows, {})

    kinds = [
        line.split(" | ")[0] for line in lines if line.startswith(("| warft |", "| settlement |"))
    ]
    assert kinds == ["| warft", "| settlement"]


def test_the_line_of_a_kind_counts_its_rows_by_state(world: Path) -> None:
    warft = {"kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft"}
    rows = [warft | {"id": "open"}, warft | {"id": "skipped", "status": "skip"}]
    results = {"open": MatchResult(Outcome.AMBIGUOUS, "two of them")}

    lines = report_lines(world, rows, results)

    assert "| warft | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |" in lines


def test_an_open_row_the_run_has_no_result_for_counts_as_not_found(world: Path) -> None:
    assert "| settlement | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |" in report_lines(world, [KAAMP], {})


def test_the_total_counts_a_row_of_every_state_in_its_column(world: Path) -> None:
    lines = report_lines(world, EVERY_STATE, EVERY_STATE_RESULTS)

    assert (
        "| **total** | **1** | **2** | **1** | **1** | **2** | **1** | **1** | **1** | **10** |"
        in lines
    )


# ----------------------------------------------------- the ambiguous rows ---
def test_the_ambiguous_heading_counts_its_rows(world: Path) -> None:
    assert "## Ambiguous (1)" in report_lines(world, EVERY_STATE, EVERY_STATE_RESULTS)


def test_an_ambiguous_row_is_listed_with_its_hint_why_and_candidates(world: Path) -> None:
    warft = {"id": "schoerkewaerw", "kind": "warft", "mooring": "Schörkewärw"}
    rows = [warft | {"de": "Kirchwarft", "hint": "Hooge"}]

    lines = report_lines(world, rows, EVERY_STATE_RESULTS)

    assert (
        "| schoerkewaerw | 2 | warft | Schörkewärw | Kirchwarft | Hooge "
        "| location hint 'Hooge' matched no cluster "
        "| `n/11711096159:Kirchwarft:hamlet:27;n/1333738478:Kirchwarft:hamlet:6` |"
    ) in lines


# ----------------------------------------------------- the rows not found ---
def test_the_not_found_heading_counts_its_rows(world: Path) -> None:
    assert "## Not found (2)" in report_lines(world, EVERY_STATE, EVERY_STATE_RESULTS)


def test_a_row_not_found_is_listed_with_why_and_its_near_misses(world: Path) -> None:
    street = ranked("w", 1, 8.9, 54.7, name="Kampen", highway="residential")
    results = {"kaamp": MatchResult(Outcome.NOT_FOUND, "no settlement", candidates=(street,))}

    lines = report_lines(world, [KAAMP], results)

    assert (
        "| kaamp | 2 | settlement | Kaamp | Kampen | no settlement | `w/1:Kampen:residential:0` |"
        in (lines)
    )


def test_an_open_row_without_a_result_is_listed_without_note_or_near_misses(
    world: Path,
) -> None:
    assert "| kaamp | 2 | settlement | Kaamp | Kampen |  |  |" in report_lines(world, [KAAMP], {})


def test_a_row_without_a_german_name_is_listed_with_its_danish_one(world: Path) -> None:
    wiringhiird = {"id": "wiringhiird", "kind": "landscape", "mooring": "Wiringhiird"}
    rows = [wiringhiird | {"da": "Vidingherred"}]

    lines = report_lines(world, rows, {})

    assert "| wiringhiird | 2 | landscape | Wiringhiird | Vidingherred |  |  |" in lines


# -------------------------------------------------------------- the stamp ---
def test_the_report_ends_with_the_stamp_it_was_written_from(world: Path) -> None:
    assert report_of(world, [KAAMP], {}).endswith(
        '\n<!-- built_from: {"places.csv":"ce013625030ba8dba906f756967f9e9ca394464a",'
        '"extracts":[]} -->\n'
    )


# --------------------------------------------------------- the candidates ---
def test_the_report_lists_the_first_twenty_candidates_and_how_many_more_there_are() -> None:
    assert matchreport.report_cands(KAMPEN_STREETS) == KAMPEN_STREETS_SHOWN + ";... (+2 more)"


def test_the_report_cuts_a_candidates_name_to_forty_characters(world: Path) -> None:
    long = ranked("n", 1, 8.9, 54.7, name="Kampen " + "x" * 40, place="hamlet")
    assert f"`n/1:Kampen {'x' * 33}:hamlet:0`" in with_candidate(world, long)


def test_the_report_says_when_a_candidate_has_no_position(world: Path) -> None:
    unplaced = cand("r", 1, None, None, name="Kampen", place="hamlet")
    nowhere: RankedCandidate = {**unplaced, "rank": 0, "byname": False}
    assert "`r/1:Kampen:hamlet:?`" in with_candidate(world, nowhere)


def test_the_report_replaces_the_last_one_in_one_step(world: Path) -> None:
    # never half written: the old file stays whole under its other name
    (world / "REPORT.md").write_text("# an older report\n", encoding="utf-8")
    os.link(world / "REPORT.md", world / "kept.md")
    with_candidate(world, ranked("n", 1, 8.9, 54.7, name="Kampen", place="hamlet"))
    assert (world / "kept.md").read_text(encoding="utf-8") == "# an older report\n"
