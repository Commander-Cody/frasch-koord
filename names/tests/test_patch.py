"""Reading the decision patch of the curation view (frasch.patch): the last
line per row counts, and no line is lost."""

from __future__ import annotations

import json
from pathlib import Path

from frasch import patch
from conftest import read_schema


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


def read_entries(path: Path) -> list[patch.PatchEntry]:
    """The entries `read_patch` keeps, all of them valid."""
    lines = patch.read_patch(path)
    assert all(isinstance(line, patch.EntryLine) for line in lines)
    return [line.entry for line in lines if isinstance(line, patch.EntryLine)]


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
    patch.read_patch(p, lambda number, error: broken.append(number))
    assert broken == [3]


def test_each_entry_knows_its_line_in_the_patch(tmp_path: Path) -> None:
    p = tmp_path / "curate-patch.jsonl"
    write_patch(
        p,
        entry(2, "Mursem", "Morsum", action="skip"),
        "",
        entry(4, "Hoonebel", "Hunnebüll", action="skip"),
    )
    assert [line.number for line in patch.read_patch(p)] == [1, 3]


def test_an_empty_wikidata_id_is_refused(tmp_path: Path) -> None:
    # a decision without a Wikidata id leaves the field out
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="osm", osm="node/1", wikidata=""))
    (line,) = patch.read_patch(p)
    assert isinstance(line, patch.RefusedLine)


def test_every_action_of_the_patch_schema_has_its_branch() -> None:
    schema = read_schema("curate-patch")
    branches = [branch["if"]["properties"]["action"]["const"] for branch in schema["allOf"]]
    assert branches == schema["properties"]["action"]["enum"]
