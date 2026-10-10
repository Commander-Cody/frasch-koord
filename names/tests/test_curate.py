"""`frasch curate`: reading back the matcher's `candidates` cell, reading the
decision patch, the export of the worklist and the command line.  (`apply`
itself is covered in test_curate_apply.py.)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import curate
from frasch import match
from frasch.__main__ import main
from frasch.candidates import Candidate
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


def rec(t: str, id: int, lon: float | None, lat: float | None, **tags: str) -> Candidate:
    return {
        "src": "schleswig-holstein",
        "t": t,
        "id": id,
        "lon": lon,
        "lat": lat,
        "tags": tags,
    }


KAMPEN_SYLT = rec("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)", place="village")


# ------------------------------------------------------- parse_candidates ---
def test_candidate_round_trips_through_fmt_cand() -> None:
    (c,) = curate.parse_candidates(match.fmt_cand(KAMPEN_SYLT))
    assert c["key"] == ("n", 240063898)
    assert c["ref"] == "node/240063898"
    assert c["name"] == "Kampen (Sylt)"
    assert c["class"] == "village"
    # 28.2 km north and 35.6 km west of the North Frisia centre (8.9, 54.7)
    assert c["km"] == 45


def test_candidate_class_falls_back_past_place() -> None:
    peninsula = rec("n", 6337086093, 8.865555, 54.487371, name="Nordstrand", natural="peninsula")
    (c,) = curate.parse_candidates(match.fmt_cand(peninsula))
    assert (c["ref"], c["class"]) == ("node/6337086093", "peninsula")


def test_candidate_name_with_a_colon_survives() -> None:
    odd = rec("w", 188800550, 8.9, 54.7, name="Warft: Kirchwarft", landuse="residential")
    (c,) = curate.parse_candidates(match.fmt_cand(odd))
    assert c["name"] == "Warft: Kirchwarft"
    assert c["class"] == "residential"
    assert c["km"] == 0


def test_candidate_without_position_has_no_distance() -> None:
    nowhere = rec("r", 1420394, None, None, name="Holm", boundary="administrative")
    (c,) = curate.parse_candidates(match.fmt_cand(nowhere))
    assert c["ref"] == "relation/1420394"
    assert c["km"] is None


def test_several_candidates_keep_their_order() -> None:
    hooge = rec("n", 11711096159, 8.544362, 54.572982, name="Kirchwarft", place="hamlet")
    ockholm = rec("n", 1333738478, 8.826992, 54.664965, name="Kirchwarft", place="hamlet")
    cell = ";".join([match.fmt_cand(hooge), match.fmt_cand(ockholm)])
    assert [c["ref"] for c in curate.parse_candidates(cell)] == [
        "node/11711096159",
        "node/1333738478",
    ]


def test_unreadable_candidate_is_skipped() -> None:
    cell = "x/1:Holm:village:3;" + match.fmt_cand(KAMPEN_SYLT)
    assert [c["ref"] for c in curate.parse_candidates(cell)] == ["node/240063898"]


def test_empty_candidates_cell_is_no_candidate() -> None:
    assert curate.parse_candidates("") == []
    assert curate.parse_candidates(None) == []


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


def test_broken_and_blank_lines_are_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="skip"),
        "",
        '{"line": 3, "kind": "sett',
        entry(4, "Hoonebel", "Hunnebüll", action="skip"),
    )
    assert [e.get("line") for e in read_entries(p)] == [2, 4]
    assert ":3: not JSON" in capsys.readouterr().err


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
def write_matches(path: Path, *rows: tuple[str, str, str, str]) -> Path:
    """A work/matches.csv of (id, result, candidates, note) rows -- the
    columns export reads."""
    lines = ["id,result,candidates,note", *(",".join(r) for r in rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


SYLT = cand("r", 2000, 8.3, 54.9, name="Sylt", place="island")
KAMPEN = cand("n", 240063898, 8.344065, 54.95377, name="Kampen", place="village", wikidata="Q1")
KAMPEN_DK = cand("n", 7, 8.9, 54.7, src="denmark", name="Kampen", place="hamlet")
KAMPEN_GONE = rec("w", 5, 8.9, 54.7, name="Kampen", landuse="residential")  # not in the file

EXPORT_PLACES = [
    {"id": "kirchwarft", "kind": "warft", "mooring": "Schörkewärw", "hint": "Nirgendwo"},
    {"id": "kampen", "kind": "settlement", "mooring": "Kaamp", "de": "Kampen", "hint": "Sylt"},
    {"id": "hus", "kind": "settlement", "mooring": "Hüs", "osm": "node/9", "status": "ok"},
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "hint": "Karrharde; alt"},
    {"id": "bol", "kind": "settlement", "mooring": "Bol", "da": "Bøl", "hint": "Karrharde"},
]


def export(world: Path) -> None:
    write_candidates(world / "work" / "candidates.jsonl", SYLT, KAMPEN, KAMPEN_DK)
    curate.export(workspace(world), REGISTRY)


def export_the_review_rows(world: Path) -> Path:
    """Export EXPORT_PLACES after a match that left three of its rows for
    review, a decided and a deleted one, and one it matched; -> the worklist."""
    (world / "places.csv").write_text(places_text(EXPORT_PLACES), encoding="utf-8")
    kampen_cell = ";".join(match.fmt_cand(c) for c in (KAMPEN, KAMPEN_DK, KAMPEN_GONE))
    write_matches(
        world / "work" / "matches.csv",
        ("kirchwarft", "not_found", "", "no candidate"),
        ("kampen", "ambiguous", kampen_cell, "3 clusters"),
        ("hus", "ambiguous", "", "decided by hand since"),  # unowned
        ("gone", "not_found", "", "deleted since"),  # stale
        ("toftem", "ok", "", ""),  # not for the worklist
        ("bol", "not_found", "", "too far"),
    )
    export(world)
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
    write_matches(world / "work" / "matches.csv", ("ripen", "not_found", "", "no candidate"))
    export(world)
    (row,) = json.loads((world / "work" / "curate.json").read_text(encoding="utf-8"))["rows"]
    assert (row["name_de"], row["name_da"]) == ("Ripen", "Ribe")


def test_export_writes_the_worklist_and_reports_what_it_left_out(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = export_the_review_rows(world)
    assert capsys.readouterr().out == (
        f"read {world / 'work' / 'candidates.jsonl'}: kept 3 records "
        f"(3 candidates, 2 hint names, 0s)\n"
        f"wrote 3 rows to {out} (2 kB): 1 ambiguous, 2 not found; "
        f"2 candidates with a position, 2 rows with a hint point\n"
        "note: 1 row(s) have been decided by hand since work/matches.csv "
        "was written -- not exported\n"
        "note: 1 row(s) of work/matches.csv are no longer in places.csv "
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
        "why": "3 clusters",
        "hint_point": [8.3, 54.9, 25.0],  # Sylt is a large hint
        "candidates": [
            {
                "ref": "node/240063898",
                "name": "Kampen",
                "class": "village",
                "km": 45,  # as KAMPEN_SYLT above
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
            {
                "ref": "way/5",
                "name": "Kampen",
                "class": "residential",
                "km": 0,
                "lon": None,
                "lat": None,
                "tags": "",
                "in_sh": False,
            },
        ],
    }
    assert (bol["names"], bol["da"], bol["why"]) == ({"mooring": "Bol"}, "Bøl", "too far")
    assert bol["hint_point"] == [9.02, 54.8, 15.0]  # Karrharde, a fixed circle
    assert (warft["result"], warft["hint_point"], warft["candidates"]) == ("not_found", None, [])


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
