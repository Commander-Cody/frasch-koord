"""`frasch curate export` (frasch.worklist): the rows the matcher left for a
human, as the curation view reads them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import match, matchfile, worklist
from conftest import (
    REGISTRY,
    cand,
    places_text,
    read_schema,
    schema_problems,
    workspace,
    write_candidates,
)


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


def export(world: Path, *matches: matchfile.Entry) -> worklist.ExportReport:
    """Export the worklist of a name list `matches` is the matches file of."""
    matchfile.write(str(world / "work" / "matches.jsonl"), matches)
    return worklist.export(workspace(world), REGISTRY)


def report_of_the_review_rows(world: Path) -> worklist.ExportReport:
    """Export EXPORT_PLACES after a match that left three of its rows for
    review, a decided and a deleted one, and one it matched; -> the report."""
    (world / "places.csv").write_text(places_text(EXPORT_PLACES), encoding="utf-8")
    return export(
        world,
        left("kirchwarft", "not_found", "no candidate"),
        left("kampen", "ambiguous", "2 clusters", KAMPEN, KAMPEN_DK, hint_point=[8.3, 54.9, 25.0]),
        left("hus", "ambiguous", "decided by hand since"),  # unowned
        left("gone", "not_found", "deleted since"),  # stale
        MATCHED,  # not for the worklist
        left("bol", "not_found", "too far", hint_point=[9.02, 54.8, 15.0]),
    )


def export_the_review_rows(world: Path) -> Path:
    """Export as `report_of_the_review_rows`; -> the worklist."""
    report_of_the_review_rows(world)
    return world / "work" / "curate.json"


def test_the_exported_worklist_keeps_its_schema(world: Path) -> None:
    exported = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert schema_problems(exported, "curate-worklist") == []


def test_the_worklist_names_the_class_tags_the_most_telling_first(world: Path) -> None:
    exported = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert exported["class_keys"] == [
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
    exported = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert exported["settlement_places"] == [
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
    exported = json.loads(export_the_review_rows(world).read_text(encoding="utf-8"))
    assert exported["results"] == read_schema("curate-worklist")["$defs"]["result"]["enum"]


def exported_row(world: Path, place: dict[str, str]) -> dict[str, object]:
    """The worklist row of `place`, the one row of a list the matcher found
    nothing for."""
    (world / "places.csv").write_text(places_text([place]), encoding="utf-8")
    export(world, left(place["id"], "not_found", "no candidate"))
    (row,) = json.loads((world / "work" / "curate.json").read_text(encoding="utf-8"))["rows"]
    return dict(row)


def test_a_row_is_exported_with_its_primary_german_and_danish_names(world: Path) -> None:
    ripen = {"id": "ripen", "kind": "settlement", "mooring": "Ripen"}
    cells = {"de": "Ripen; Riepen (alt)", "da": "Ribe?"}
    row = exported_row(world, ripen | cells)
    assert (row["name_de"], row["name_da"]) == ("Ripen", "Ribe")


def test_a_row_suggests_the_slug_of_its_german_name_folded_like_a_row_id(world: Path) -> None:
    burg = {"id": "e-borj", "kind": "settlement", "mooring": "e Borj", "de": "Deezbüll Burg"}
    assert exported_row(world, burg)["slug_suggestion"] == "deezbull-burg"


def test_a_row_without_a_german_name_suggests_the_slug_of_its_frisian_one(world: Path) -> None:
    bridge = {"id": "bro", "kind": "road", "mooring": "Hansbäistååkbro"}
    assert exported_row(world, bridge)["slug_suggestion"] == "hansbaistaakbro"


def test_export_prints_nothing(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # it is called as a library too (`frasch update`): the command prints
    export_the_review_rows(world)
    assert capsys.readouterr() == ("", "")


def test_export_reports_what_it_wrote_and_what_it_left_out(world: Path) -> None:
    assert report_of_the_review_rows(world).log == [
        f"wrote 3 rows to {world / 'work' / 'curate.json'} (2 kB): 1 ambiguous, 2 not found; "
        f"2 candidates with a position, 2 rows with a hint point",
        "note: 1 row(s) have been decided by hand since work/matches.jsonl "
        "was written -- not exported",
        "note: 1 row(s) of work/matches.jsonl are no longer in places.csv "
        "(stale, re-run `frasch match`)",
    ]


def test_export_writes_the_worklist(world: Path) -> None:
    out = export_the_review_rows(world)
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["bbox"] == [7.8, 54.15, 9.55, 55.12]
    assert exported["kind_order"] == [
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
    assert sorted(exported["polygon_kinds"]) == [
        "hallig",
        "harde",
        "island",
        "koog",
        "landscape",
        "sand",
    ]
    # settlements before the warft, each kind in places.csv order
    kampen, bol, warft = exported["rows"]
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
        "slug_suggestion": "kampen",
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


def test_an_export_does_not_cut_off_who_is_reading_the_worklist(world: Path) -> None:
    # the dev server hands the file out while `frasch update` exports again
    out = export_the_review_rows(world)
    before = out.read_text(encoding="utf-8")
    with open(out, encoding="utf-8") as reader:
        export(world)  # a match that left nothing: another, shorter worklist
        assert reader.read() == before


def test_a_candidate_named_with_a_semicolon_and_a_colon_reaches_the_worklist(world: Path) -> None:
    # two hamlets the list's Kirchwarft can be, one of them under two names
    odd = cand("n", 1, 8.54, 54.57, name="Kirchwarft; Hooge: Schörkewärw", place="hamlet")
    plain = cand("n", 2, 8.83, 54.66, name="Kirchwarft", place="hamlet")
    warft = {"id": "schoerkewaerw", "kind": "warft", "mooring": "Schörkewärw", "de": "Kirchwarft"}
    (world / "places.csv").write_text(places_text([warft]), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", odd, plain)
    match.run(workspace(world), REGISTRY, offline=True)
    worklist.export(workspace(world), REGISTRY)
    (row,) = json.loads((world / "work" / "curate.json").read_text(encoding="utf-8"))["rows"]
    assert [c["name"] for c in row["candidates"]] == [
        "Kirchwarft",
        "Kirchwarft; Hooge: Schörkewärw",
    ]
