"""`frasch check-inputs` reports every problem in the hand-edited name files, each with
its line, instead of stopping at the first one (#22, M3)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import pytest

from frasch import check_inputs, placelist, tables
from frasch.__main__ import main
from frasch.errors import Problem
from frasch.paths import Workspace
from conftest import CURATION_HEADER, REGISTRY, TOFTUM, places_text

NIEBUELL = {
    "kind": "settlement",
    "mooring": "Naibel",
    "de": "Niebüll",
    "osm": "node/240042766",
    "wikidata": "Q21003",
    "status": "ok",
}


class CheckNames(Protocol):
    def __call__(
        self, places: str, curation: str = ..., dialects: str | None = ...
    ) -> list[Problem]: ...


@pytest.fixture
def names(ws: Workspace) -> CheckNames:
    """Write places.csv (and optionally curation.csv and dialects.csv) into
    the workspace and return what `check` finds in it."""

    def run(
        places: str, curation: str = CURATION_HEADER, dialects: str | None = None
    ) -> list[Problem]:
        Path(ws.names).write_text(places, encoding="utf-8")
        Path(ws.curation).write_text(curation, encoding="utf-8")
        if dialects is not None:
            Path(ws.dialects).write_text(dialects, encoding="utf-8")
        return check_inputs.check(ws)

    return run


def lines(problems: Sequence[Problem]) -> list[int]:
    return [p.line for p in problems]


def test_a_well_formed_list_has_no_problems(names: CheckNames) -> None:
    assert names(places_text([TOFTUM, NIEBUELL])) == []


def test_a_row_missing_a_comma_is_reported_with_its_line(names: CheckNames) -> None:
    # Dropping one comma used to shift every later cell one column left
    # without a word: Toftem ended up in `local`, the German name in `hint`.
    text = places_text([NIEBUELL, TOFTUM])
    broken = text.replace("Toftem,,", "Toftem,", 1)
    problems = names(broken)
    assert lines(problems) == [3]
    assert "cells" in problems[0].message


def test_every_problem_is_reported_not_only_the_first(names: CheckNames) -> None:
    problems = names(
        places_text(
            [
                {**TOFTUM, "kind": "villlage"},
                {**NIEBUELL, "status": "done"},
            ]
        )
    )
    assert [(p.line, p.message.split(" ")[:2]) for p in problems] == [
        (2, ["unknown", "kind"]),
        (3, ["unknown", "status"]),
    ]


def test_a_byte_order_mark_from_a_spreadsheet_export_is_fine(names: CheckNames) -> None:
    # Excel's "CSV UTF-8" puts one in front of the header, which used to turn
    # `kind` into `﻿kind`: "missing column(s) ['kind']".
    assert names("﻿" + places_text([TOFTUM])) == []


def test_a_semicolon_separated_export_gets_one_clear_message(names: CheckNames) -> None:
    # A German-locale spreadsheet saves "CSV" with `;` between the cells.
    text = places_text([TOFTUM, NIEBUELL]).replace(",", ";")
    problems = names(text)
    assert lines(problems) == [1]
    assert "`;`" in problems[0].message


def test_a_missing_column_is_reported_on_the_header(names: CheckNames) -> None:
    text = places_text([TOFTUM]).replace(",hint,", ",", 1)
    text = "\n".join(
        line.replace(",,", ",", 1) if i else line for i, line in enumerate(text.split("\n"))
    )
    problems = names(text)
    assert lines(problems) == [1]
    assert "hint" in problems[0].message


def test_a_column_named_twice_is_reported(names: CheckNames) -> None:
    # csv.DictReader keeps the last one and drops the other without a word.
    head, *rest = places_text([TOFTUM]).split("\n")
    text = "\n".join([head + ",de"] + [r + "," for r in rest if r]) + "\n"
    problems = names(text)
    assert lines(problems) == [1]
    assert "de" in problems[0].message


@pytest.mark.parametrize(
    "cell",
    [
        "Toftem (Foortuftinge; Taftem",  # unclosed remark: became one name with a `(`
        "Toftem) (Foortuftinge)",  # stray closing bracket
        "Toftem (Foortuftinge) Taftem",  # text after the remark: "Toftem  Taftem"
        "Toftem?",  # `?` used to be stripped; say `uncertain` in note
        "Toftem;Taftem",  # not the canonical `; `
        "Toftem ; Taftem",
        "Toftem;  Taftem",
        "Toftem; ; Taftem",  # an empty variant
        "Toftem;",
    ],
)
def test_a_malformed_name_cell_is_reported(names: CheckNames, cell: str) -> None:
    problems = names(places_text([{**TOFTUM, "mooring": cell}]))
    assert lines(problems) == [2]
    assert "mooring" in problems[0].message


@pytest.mark.parametrize(
    "cell",
    [
        "Huađer; Huuger (Sölring; Wisinge)",  # a `;` inside a remark splits nothing
        "Brouersweerw (Foortuftinge)",
        "Toftem (Foortuftinge) (Hoekstra 2015)",
        "et Dånsch",
    ],
)
def test_a_well_formed_name_cell_is_fine(names: CheckNames, cell: str) -> None:
    assert names(places_text([{**TOFTUM, "mooring": cell}])) == []


def test_a_variant_repeated_in_one_cell_is_reported(names: CheckNames) -> None:
    problems = names(places_text([{**TOFTUM, "mooring": "Toftem; Taftem; Toftem (Foortuftinge)"}]))
    assert lines(problems) == [2]
    assert "Toftem" in problems[0].message


@pytest.mark.parametrize(
    "cells",
    [
        {"osm": "node/abc"},
        {"osm": "Node/240044107"},
        {"osm": "node/240044107;way/12"},  # canonical `; ` as in name cells
        {"osm": "local/toftum; node/240044107"},  # a local reference stands alone
        {"wikidata": "21003"},
    ],
)
def test_a_malformed_reference_is_reported(names: CheckNames, cells: dict[str, str]) -> None:
    problems = names(places_text([{**TOFTUM, **cells}]))
    assert lines(problems) == [2]


def test_an_osm_object_claimed_by_two_rows_is_reported_on_the_second(names: CheckNames) -> None:
    # Only one of the two names can end up on the map.
    problems = names(
        places_text(
            [
                {
                    "kind": "warft",
                    "mooring": "Lungendik",
                    "de": "Langedeich",
                    "osm": "way/28330569",
                    "status": "ok",
                },
                TOFTUM,
                {
                    "kind": "warft",
                    "mooring": "Lungedik",
                    "de": "Langerdeich",
                    "osm": "way/1; way/28330569",
                    "status": "auto",
                },
            ]
        )
    )
    assert lines(problems) == [4]
    assert "way/28330569" in problems[0].message
    assert "line 2" in problems[0].message


def test_a_skipped_row_may_share_an_object(names: CheckNames) -> None:
    assert (
        names(
            places_text(
                [
                    TOFTUM,
                    {**TOFTUM, "mooring": "Taftem", "status": "skip"},
                ]
            )
        )
        == []
    )


def test_a_wikidata_item_on_two_rows_is_reported_on_the_second(names: CheckNames) -> None:
    problems = names(
        places_text([NIEBUELL, TOFTUM, {**TOFTUM, "osm": "node/7", "wikidata": "Q21003"}])
    )
    assert lines(problems) == [4]
    assert "Q21003" in problems[0].message
    assert "line 2" in problems[0].message


HUELLTOFT = {
    "kind": "settlement",
    "mooring": "Hültoft",
    "de": "Hülltoft",
    "osm": "local/huelltoft",
    "status": "ok",
}
HUELLTOFT_POS = "local/huelltoft,Hülltoft,54.881287,8.771304,,,,,\n"


def test_a_local_reference_with_its_position_is_fine(names: CheckNames) -> None:
    assert names(places_text([HUELLTOFT]), CURATION_HEADER + HUELLTOFT_POS) == []


def test_a_local_reference_without_a_position_is_reported(names: CheckNames) -> None:
    # The injector has nowhere to put the place, and the search cannot find it.
    problems = names(places_text([TOFTUM, HUELLTOFT]))
    assert lines(problems) == [3]
    assert "local/huelltoft" in problems[0].message


def test_a_local_reference_with_a_wikidata_id_is_reported(names: CheckNames) -> None:
    # A local reference is for a place OSM does not have; one Wikidata knows
    # belongs in OSM.
    problems = names(
        places_text([{**HUELLTOFT, "wikidata": "Q1"}]), CURATION_HEADER + HUELLTOFT_POS
    )
    assert lines(problems) == [2]
    assert "wikidata" in problems[0].message


@pytest.mark.parametrize(
    "row",
    [
        "node/abc,Toftum,,,,,,,",
        "way/28330569,Lungendik,54.6,8.7,,,,,",  # lat/lon only go with local/
        "local/westerheide-amrum,Westerheide,,,,,,,",  # ... and a local one needs them
        "local/westerheide-amrum,Westerheide,54.65,,,,,,",
        "local/westerheide-amrum,Westerheide,54°39',8.34,,,,,",
        "local/westerheide-amrum,Westerheide,95,8.34,,,,,",
        "way/177387348,Habel,,,place,,,,",  # set_tags are key=value
        "way/177387348,Habel,,,=island,,,,",
        "way/177387348,Habel,,,place=island,twelve,,,",
        "way/177387348,Habel,,,place=island,,1.5,,",
        "node/1,Pellworm,,,,,,-3,",  # polygon_km2 is a positive area
        "way/1,Pellworm,,,,,,3,",  # ... around one node
    ],
)
def test_a_damaged_curation_row_is_reported(names: CheckNames, row: str) -> None:
    problems = names(places_text([TOFTUM]), CURATION_HEADER + row + "\n")
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("curation.csv", 2)]


def test_a_local_reference_positioned_twice_is_reported(names: CheckNames) -> None:
    problems = names(places_text([HUELLTOFT]), CURATION_HEADER + HUELLTOFT_POS * 2)
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("curation.csv", 3)]


def command(ws: Workspace, *options: str) -> int:
    """`frasch check-inputs` on the files of the workspace."""
    files = ["--names", ws.names, "--curation", ws.curation, "--dialects", ws.dialects]
    return main(
        ["check-inputs", *files, "--area-list", ws.area_list, "--work", str(work(ws)), *options]
    )


def work(ws: Workspace) -> Path:
    return Path(ws.lock).parent


def test_the_command_fails_and_prints_each_problem_with_its_place(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    Path(ws.names).write_text(places_text([TOFTUM, {**NIEBUELL, "kind": "town"}]), encoding="utf-8")
    assert command(ws) == 1
    assert capsys.readouterr().out.startswith(f"{ws.names}:3: unknown kind 'town'")


def test_the_command_succeeds_on_a_clean_list(ws: Workspace) -> None:
    Path(ws.names).write_text(places_text([TOFTUM]), encoding="utf-8")
    assert command(ws) == 0


REGISTRY_HEADER = "tag,column,label,status,view,note\n"
MOORING = "frr-x-mooring,mooring,Mooring,living,yes,\n"


@pytest.mark.parametrize(
    "row",
    [
        "frr-x-mooringen,mooringen,Mooring,living,yes,\n",  # subtag longer than 8
        "mooring,mooring,Mooring,living,yes,\n",  # not frr-x-…
        "frr-x-mooring,Mooring,Mooring,living,yes,\n",  # column not lowercase
        "frr-x-local,local,Local,living,yes,\n",  # `local` is reserved
        "frr-x-mooring,mooring,Mooring,alive,yes,\n",
        "frr-x-mooring,mooring,Mooring,living,maybe,\n",
        "frr-x-mooring,mooring,,living,yes,\n",
    ],
)
def test_a_damaged_dialect_row_is_reported(names: CheckNames, row: str) -> None:
    problems = names(places_text([TOFTUM]), dialects=REGISTRY_HEADER + row)
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("dialects.csv", 2)]


def test_a_dialect_registered_twice_is_reported(names: CheckNames) -> None:
    problems = names(places_text([TOFTUM]), dialects=REGISTRY_HEADER + MOORING * 2)
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("dialects.csv", 3)]


def test_a_registry_without_dialects_is_reported_not_a_crash(names: CheckNames) -> None:
    # as registry.read refuses it: without a dialect no name column exists
    problems = names(places_text([TOFTUM]), dialects=REGISTRY_HEADER + "\n")
    assert [(os.path.basename(p.path), p.line, p.message) for p in problems] == [
        ("dialects.csv", 1, "no dialects")
    ]


def test_the_command_can_add_its_problems_to_a_markdown_summary(ws: Workspace, world: Path) -> None:
    # CI passes $GITHUB_STEP_SUMMARY, so a broken places.csv shows on the
    # run's page and not only in its log.
    places, summary = world / "places.csv", world / "summary.md"
    places.write_text(places_text([TOFTUM, {**NIEBUELL, "kind": "town"}]), encoding="utf-8")
    summary.write_text("earlier step\n", encoding="utf-8")
    command(ws, "--summary", str(summary))
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n")  # appended, not replaced
    assert "places.csv:3" in text
    assert "unknown kind 'town'" in text


def test_a_clean_list_says_so_in_the_summary(ws: Workspace, world: Path) -> None:
    places, summary = world / "places.csv", world / "summary.md"
    places.write_text(places_text([TOFTUM]), encoding="utf-8")
    check_inputs.run(ws, summary=str(summary))
    assert "no problems" in summary.read_text(encoding="utf-8")


def test_a_second_polygon_for_one_node_is_reported(names: CheckNames) -> None:
    # The tile build refuses it, so the check must too.
    row = "node/85929111,Nordstrand,,,place=island,,,50,\n"
    problems = names(places_text([TOFTUM]), CURATION_HEADER + row * 2)
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("curation.csv", 3)]


@pytest.mark.parametrize(
    "row",
    [
        "local/huelltoft,Hülltoft,54.881287,8.771304,,,,\n",  # a comma too few
        "local/huelltoft,Hülltoft,54.881287,8.771304,,,,,,\n",  # a comma too many
    ],
)
def test_a_curation_row_with_the_wrong_number_of_cells_is_reported(
    names: CheckNames, row: str
) -> None:
    # Its columns shift: a zoom lands in `set_tags`, a position in `name`.
    problems = names(places_text([HUELLTOFT]), CURATION_HEADER + row)
    assert ("curation.csv", 2) in [(os.path.basename(p.path), p.line) for p in problems]
    assert any("cells" in p.message for p in problems)


def test_a_curation_file_without_one_of_its_columns_is_reported(names: CheckNames) -> None:
    # `frasch curate apply` refuses such a file; the check must not pass it.
    problems = names(places_text([TOFTUM]), "osm,name,lat,lon,minzoom,maxzoom,polygon_km2,note\n")
    assert [(os.path.basename(p.path), p.line, p.message) for p in problems] == [
        ("curation.csv", 1, "missing column(s) set_tags")
    ]


def test_a_dialect_row_with_the_wrong_number_of_cells_is_reported(names: CheckNames) -> None:
    problems = names(
        places_text([TOFTUM]),
        dialects=REGISTRY_HEADER + "frr-x-mooring,mooring,Mooring,living,yes\n",
    )
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("dialects.csv", 2)]
    assert "cells" in problems[0].message


def test_a_blank_line_is_no_problem_and_keeps_the_line_numbers(names: CheckNames) -> None:
    # The reader skips it, so the check does too; the rows after it are
    # still reported at the line an editor sees them on.
    head, first, second, _ = places_text([TOFTUM, {**NIEBUELL, "kind": "town"}]).split("\n")
    problems = names("\n".join([head, first, "", second]) + "\n")
    assert lines(problems) == [4]
    assert "town" in problems[0].message


# ------------------------------------------------------------------ ids ---
def test_a_row_without_an_id_is_reported(names: CheckNames) -> None:
    problems = names(places_text([TOFTUM, {**NIEBUELL, "id": ""}]))
    assert lines(problems) == [3]
    assert "check-inputs --fix" in problems[0].message


def test_an_id_used_twice_is_reported_on_the_second_row(names: CheckNames) -> None:
    problems = names(places_text([{**TOFTUM, "id": "toftem"}, {**NIEBUELL, "id": "toftem"}]))
    assert [(p.line, p.message) for p in problems] == [(3, "id toftem is already used on line 2")]


def fix(ws: Workspace) -> list[Problem]:
    """Give the new rows an id and check the workspace; -> what is wrong with it."""
    return check_inputs.run(ws, fix=True).problems


def test_fix_gives_each_new_row_an_id_from_its_frisian_name(ws: Workspace, world: Path) -> None:
    places = world / "places.csv"
    places.write_text(
        places_text(
            [
                {**NIEBUELL, "id": ""},
                {"kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft", "id": ""},
                {"kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft", "id": ""},
                {"kind": "country", "de": "Dänemark", "wikidata": "Q35", "id": ""},
                {**TOFTUM, "id": "toftem"},
                {
                    "kind": "settlement",
                    "mooring": "Toftem",
                    "de": "Toftum",
                    "osm": "node/7",
                    "id": "",
                },
            ]
        ),
        encoding="utf-8",
    )
    assert fix(ws) == []
    rows, _ = placelist.read(str(places), REGISTRY)
    assert [r["id"] for r in rows] == [
        "naibel",
        "schorkewarw",
        "schorkewarw-2",
        "danemark",
        "toftem",
        "toftem-2",
    ]


def test_fix_reports_a_semicolon_separated_list_as_such(
    ws: Workspace, world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # It used to look for its columns in `<the one cell>, id` and miss them all.
    places = world / "places.csv"
    places.write_text(places_text([TOFTUM]).replace(",", ";"), encoding="utf-8")
    fix(ws)
    assert f"no id given: {places}:1: {tables.SEMICOLON_SEPARATED}\n" in capsys.readouterr().err


def test_a_list_without_the_id_column_is_reported_on_the_header(names: CheckNames) -> None:
    without = "".join(line.rsplit(",", 1)[0] + "\n" for line in places_text([TOFTUM]).splitlines())
    assert [(p.line, p.message) for p in names(without)] == [
        (1, "missing column(s) id (`frasch check-inputs --fix` adds `id`)")
    ]


def test_fix_adds_the_id_column_to_a_list_that_has_none(ws: Workspace, world: Path) -> None:
    places = world / "places.csv"
    # `id` is the last column: cut it off every line, the header's included
    without = "".join(
        line.rsplit(",", 1)[0] + "\n" for line in places_text([TOFTUM, NIEBUELL]).splitlines()
    )
    places.write_text(without, encoding="utf-8")
    assert fix(ws) == []
    rows, fields = placelist.read(str(places), REGISTRY)
    assert fields[-1] == "id"
    assert [r["id"] for r in rows] == ["toftem", "naibel"]


def test_fix_run_twice_changes_nothing(ws: Workspace, world: Path) -> None:
    places = world / "places.csv"
    places.write_text(places_text([{**TOFTUM, "id": ""}, {**NIEBUELL, "id": ""}]), encoding="utf-8")
    fix(ws)
    once = places.read_bytes()
    fix(ws)
    assert places.read_bytes() == once


def test_a_hand_set_frasch_ref_must_name_a_row(names: CheckNames) -> None:
    # the place card finds the row a label belongs to by it (#23)
    row = "node/85929111,Nordstrand,,,frasch:ref={},12,,,\n"
    assert (
        names(places_text([{**TOFTUM, "id": "toftem"}]), CURATION_HEADER + row.format("toftem"))
        == []
    )
    problems = names(places_text([TOFTUM]), CURATION_HEADER + row.format("relation/1420555"))
    assert [(p.path.endswith("curation.csv"), p.line) for p in problems] == [(True, 2)]
    assert "frasch:ref=relation/1420555 names no row" in problems[0].message


def test_a_dialect_area_reference_on_two_rows_is_reported(ws: Workspace, world: Path) -> None:
    places = world / "places.csv"
    places.write_text(places_text([TOFTUM]), encoding="utf-8")
    areas = world / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\n"
        "frr-x-solring,relation/1147134,Sylt,\n"
        "frr-x-fering,relation/1147134,Sylt,\n",
        encoding="utf-8",
    )
    problems = check_inputs.check(ws)
    assert [(os.path.basename(p.path), p.line, p.message) for p in problems] == [
        ("dialect_areas.csv", 3, "relation/1147134 is already on line 2")
    ]


def test_a_dialect_area_node_reference_is_reported(ws: Workspace, world: Path) -> None:
    # a node can never be a polygon (#24)
    places = world / "places.csv"
    places.write_text(places_text([TOFTUM]), encoding="utf-8")
    areas = world / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\nfrr-x-solring,node/1,Not an area,\n", encoding="utf-8")
    problems = check_inputs.check(ws)
    assert [(os.path.basename(p.path), p.line) for p in problems] == [("dialect_areas.csv", 2)]
    assert "node/1" in problems[0].message


def test_fix_on_a_damaged_list_still_reports_every_problem(
    ws: Workspace, world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    places = world / "places.csv"
    text = places_text([{**TOFTUM, "id": ""}, {**NIEBUELL, "kind": "town"}, TOFTUM])
    places.write_text(text.replace("Toftem,,", "Toftem,", 1), encoding="utf-8")
    assert fix(ws) != []
    out = capsys.readouterr()
    assert "no id given" in out.err
    assert [line.split(": ")[0].rsplit(":", 1)[1] for line in out.out.splitlines()] == ["2", "3"]
