"""`frasch curate`: reading the decision patch, the export of the worklist
and the command line.  (`apply` itself is covered in test_curate_apply.py.)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import curate, match, matchfile
from frasch.__main__ import main
from conftest import (
    REGISTRY,
    cand,
    path_options,
    places_text,
    read_schema,
    schema_problems,
    workspace,
    write_candidates,
)


# -------------------------------------------------------------- read_patch ---
def write_patch(path: Path, *lines: str | dict[str, object]) -> None:
    path.write_text(
        "".join(
            (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)) + "\n" for x in lines
        ),
        encoding="utf-8",
    )


IDS = {"Mursem": "mursem", "Hoonebel": "hoonebel"}


def entry(line: int, name: str, de: str, **kw: str) -> dict[str, object]:
    return {"id": IDS[name], "line": line, "kind": "settlement", "name": name, "de": de, **kw}


def read_entries(path: Path) -> list[curate.PatchEntry]:
    """The entries `read_patch` keeps, all of them valid."""
    lines = curate.read_patch(path)
    assert all(isinstance(line, curate.EntryLine) for line in lines)
    return [line.entry for line in lines if isinstance(line, curate.EntryLine)]


def test_last_decision_per_row_wins(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="skip"),
        entry(2, "Mursem", "Morsum", action="osm", osm="node/1"),
    )
    (e,) = read_entries(p)
    assert (e.get("action"), e.get("osm")) == ("osm", "node/1")


def test_patch_entries_come_back_in_line_order(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(7, "Hoonebel", "Hunnebüll", action="skip"),
        entry(2, "Mursem", "Morsum", action="skip"),
    )
    assert [e.get("line") for e in read_entries(p)] == [2, 7]


def test_same_line_but_another_row_is_a_separate_decision(tmp_path: Path) -> None:
    # the line does not identify a row: it moves when rows are added
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="skip"),
        entry(2, "Hoonebel", "Hunnebüll", action="skip"),
    )
    assert len(read_entries(p)) == 2


def test_same_row_at_another_line_is_the_same_decision(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="osm", osm="node/1"),
        entry(3, "Mursem", "Morsum", action="clear"),
    )
    (e,) = read_entries(p)
    assert e.get("action") == "clear"


def with_a_broken_line(path: Path) -> None:
    """A patch whose third line is no JSON, and its second blank."""
    write_patch(
        path,
        entry(2, "Mursem", "Morsum", action="skip"),
        "",
        '{"line": 3, "kind": "sett',
        entry(4, "Hoonebel", "Hunnebüll", action="skip"),
    )


def test_broken_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    with_a_broken_line(p)
    assert [e.get("line") for e in read_entries(p)] == [2, 4]


def test_a_line_that_is_no_json_is_handed_to_the_caller(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    with_a_broken_line(p)
    broken: list[int] = []
    curate.read_patch(p, lambda number, error: broken.append(number))
    assert broken == [3]


def test_each_entry_knows_its_line_in_the_patch(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="skip"),
        "",
        entry(4, "Hoonebel", "Hunnebüll", action="skip"),
    )
    assert [line.number for line in curate.read_patch(p)] == [1, 3]


# ------------------------------------------------------------------ export ---
def listed(
    ref: str, name: str, what: str, km: int, lon: float, lat: float, in_sh: bool, **more: str
) -> matchfile.ListedCandidate:
    """A candidate as a matches file lists it."""
    candidate: matchfile.ListedCandidate = {
        "ref": ref,
        "name": name,
        "class": what,
        "km": km,
        "lon": lon,
        "lat": lat,
        "tags": f"place={what}",
        "in_sh": in_sh,
        "rank": 0,
    }
    if "wikidata" in more:
        candidate["wikidata"] = more["wikidata"]
    return candidate


def left(
    row_id: str,
    result: str,
    why: str,
    *candidates: matchfile.ListedCandidate,
    hint_point: list[float] | None = None,
) -> matchfile.Entry:
    """The line of a matches file for a row the matcher gave no object."""
    return {
        "id": row_id,
        "result": result,
        "why": why,
        "osm": "",
        "wikidata": "",
        "match_name": "",
        "match_tags": "",
        "lon": None,
        "lat": None,
        "hint_point": hint_point,
        "candidates": list(candidates),
    }


MATCHED: matchfile.Entry = left("toftem", "matched", "") | {"osm": "node/240044107"}
KAMPEN = listed("node/240063898", "Kampen", "village", 45, 8.344065, 54.95377, True, wikidata="Q1")
KAMPEN_DK = listed("node/7", "Kampen", "hamlet", 0, 8.9, 54.7, False)

EXPORT_PLACES = [
    {"id": "kirchwarft", "kind": "warft", "mooring": "Schörkewärw", "hint": "Nirgendwo"},
    {"id": "kampen", "kind": "settlement", "mooring": "Kaamp", "de": "Kampen", "hint": "Sylt"},
    {"id": "hus", "kind": "settlement", "mooring": "Hüs", "osm": "node/9", "status": "ok"},
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "hint": "Karrharde; alt"},
    {"id": "bol", "kind": "settlement", "mooring": "Bol", "da": "Bøl", "hint": "Karrharde"},
]


def export(world: Path, *matches: matchfile.Entry) -> None:
    """Export the worklist of a name list `matches` is the matches file of."""
    matchfile.write(str(world / "work" / "matches.jsonl"), matches)
    curate.export(workspace(world), REGISTRY)


def export_the_review_rows(world: Path) -> Path:
    """Export EXPORT_PLACES after a match that left three of its rows for
    review, a decided and a deleted one, and one it matched; -> the worklist."""
    (world / "places.csv").write_text(places_text(EXPORT_PLACES), encoding="utf-8")
    export(
        world,
        left("kirchwarft", "not_found", "no candidate"),
        left("kampen", "ambiguous", "2 clusters", KAMPEN, KAMPEN_DK, hint_point=[8.3, 54.9, 25.0]),
        left("hus", "ambiguous", "decided by hand since"),  # unowned
        left("gone", "not_found", "deleted since"),  # stale
        MATCHED,  # not for the worklist
        left("bol", "not_found", "too far", hint_point=[9.02, 54.8, 15.0]),
    )
    return world / "work" / "curate.json"


def test_the_exported_worklist_keeps_its_schema(world: Path) -> None:
    worklist = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert schema_problems(worklist, "curate-worklist") == []


def test_the_worklist_names_the_class_tags_the_most_telling_first(world: Path) -> None:
    worklist = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert worklist["class_keys"] == [
        "place",
        "natural",
        "boundary",
        "waterway",
        "landuse",
        "man_made",
        "highway",
        "water",
        "historic",
    ]


def test_the_worklist_names_the_place_values_of_a_settlement(world: Path) -> None:
    worklist = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert worklist["settlement_places"] == [
        "borough",
        "city",
        "farm",
        "hamlet",
        "isolated_dwelling",
        "locality",
        "municipality",
        "neighbourhood",
        "quarter",
        "suburb",
        "town",
        "village",
    ]


def test_the_worklist_offers_the_results_of_its_schema(world: Path) -> None:
    worklist = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert worklist["results"] == read_schema("curate-worklist")["$defs"]["result"]["enum"]


def test_a_row_is_exported_with_its_primary_german_and_danish_names(world: Path) -> None:
    ripen = {"id": "ripen", "kind": "settlement", "mooring": "Ripen"}
    cells = {"de": "Ripen; Riepen (alt)", "da": "Ribe?"}
    (world / "places.csv").write_text(places_text([ripen | cells]), encoding="utf-8")
    export(world, left("ripen", "not_found", "no candidate"))
    (row,) = json.loads((world / "work" / "curate.json").read_text(encoding="utf-8"))["rows"]
    assert (row["name_de"], row["name_da"]) == ("Ripen", "Ribe")


def test_export_writes_the_worklist_and_reports_what_it_left_out(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = export_the_review_rows(world)
    assert capsys.readouterr().out == (
        f"wrote 3 rows to {out} (2 kB): 1 ambiguous, 2 not found; "
        f"2 candidates with a position, 2 rows with a hint point\n"
        "note: 1 row(s) have been decided by hand since work/matches.jsonl "
        "was written -- not exported\n"
        "note: 1 row(s) of work/matches.jsonl are no longer in places.csv "
        "(stale, re-run `frasch match`)\n"
    )
    worklist = json.loads(out.read_text(encoding="utf-8"))
    assert worklist["bbox"] == [7.8, 54.15, 9.55, 55.12]
    assert worklist["kind_order"] == [
        "settlement",
        "island",
        "hallig",
        "helgoland",
        "sand",
        "landscape",
        "water",
        "harde",
        "road",
        "country",
        "koog",
        "warft",
        "not_a_place",
    ]
    assert sorted(worklist["polygon_kinds"]) == [
        "hallig",
        "harde",
        "island",
        "koog",
        "landscape",
        "sand",
    ]
    # settlements before the warft, each kind in places.csv order
    kampen, bol, warft = worklist["rows"]
    assert [kampen["id"], bol["id"], warft["id"]] == ["kampen", "bol", "kirchwarft"]
    assert kampen == {
        "id": "kampen",
        "line": 3,
        "kind": "settlement",
        "result": "ambiguous",
        "name": "Kaamp",
        "names": {"mooring": "Kaamp"},
        "name_de": "Kampen",
        "name_da": "",
        "de": "Kampen",
        "da": "",
        "hint": "Sylt",
        "note": "",
        "why": "2 clusters",
        "hint_point": [8.3, 54.9, 25.0],
        "candidates": [
            {
                "ref": "node/240063898",
                "name": "Kampen",
                "class": "village",
                "km": 45,
                "lon": 8.344065,
                "lat": 54.95377,
                "tags": "place=village",
                "in_sh": True,
                "wikidata": "Q1",
            },
            {
                "ref": "node/7",
                "name": "Kampen",
                "class": "hamlet",
                "km": 0,
                "lon": 8.9,
                "lat": 54.7,
                "tags": "place=hamlet",
                "in_sh": False,
            },
        ],
    }
    assert (bol["names"], bol["da"], bol["why"]) == ({"mooring": "Bol"}, "Bøl", "too far")
    assert bol["hint_point"] == [9.02, 54.8, 15.0]
    assert (warft["result"], warft["hint_point"], warft["candidates"]) == ("not_found", None, [])


def test_a_candidate_named_with_a_semicolon_and_a_colon_reaches_the_worklist(world: Path) -> None:
    # two hamlets the list's Kirchwarft can be, one of them under two names
    odd = cand("n", 1, 8.54, 54.57, name="Kirchwarft; Hooge: Schörkewärw", place="hamlet")
    plain = cand("n", 2, 8.83, 54.66, name="Kirchwarft", place="hamlet")
    warft = {"id": "schoerkewaerw", "kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft"}
    (world / "places.csv").write_text(places_text([warft]), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", odd, plain)
    match.run(workspace(world), REGISTRY, offline=True)
    curate.export(workspace(world), REGISTRY)
    (row,) = json.loads((world / "work" / "curate.json").read_text(encoding="utf-8"))["rows"]
    assert [c["name"] for c in row["candidates"]] == [
        "Kirchwarft",
        "Kirchwarft; Hooge: Schörkewärw",
    ]


# ------------------------------------------------------------------- main ---
@pytest.mark.parametrize(
    "argv,hint",
    [
        (["--dry-run"], "frasch curate apply --dry-run"),
        (["--names", "places.csv", "--keep"], "frasch curate apply --names places.csv --keep"),
    ],
)
def test_an_apply_option_without_a_subcommand_points_at_apply(
    argv: list[str], hint: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["curate", *argv])
    assert exc.value.code == 2
    assert f"did you mean `{hint}`?" in capsys.readouterr().err


def test_options_without_a_subcommand_mean_export(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (world / "places.csv").write_text(places_text([]), encoding="utf-8")
    files = path_options(workspace(world), "names", "dialects", "work")
    assert main(["curate", *files]) == 1
    assert "run `frasch match` first" in capsys.readouterr().err
