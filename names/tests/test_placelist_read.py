"""`placelist.read` takes what a spreadsheet saves (#22, M3)."""
from __future__ import annotations

import pytest

import placelist
from conftest import TOFTUM, places_text



def test_reads_a_list_saved_with_a_byte_order_mark(tmp_path):
    # Excel's "CSV UTF-8" starts the file with one.
    path = tmp_path / "places.csv"
    path.write_bytes(b"\xef\xbb\xbf" + places_text([TOFTUM]).encode("utf-8"))
    rows, fields = placelist.read(str(path))
    assert fields[0] == "kind"
    assert rows[0]["mooring"] == "Toftem"


def test_refuses_a_semicolon_separated_list_with_a_clear_message(tmp_path):
    path = tmp_path / "places.csv"
    path.write_text(places_text([TOFTUM]).replace(",", ";"), encoding="utf-8")
    with pytest.raises(SystemExit, match="separated by `;`"):
        placelist.read(str(path))


def test_line_numbers_are_those_of_the_file_after_a_blank_line(tmp_path):
    # REPORT.md, curate.py and check.py all point editors at `_line`.
    head, first, second, _ = places_text([TOFTUM, {**TOFTUM, "mooring": "Taftem"}]).split("\n")
    path = tmp_path / "places.csv"
    path.write_text("\n".join([head, first, "", second]) + "\n", encoding="utf-8")
    rows, _ = placelist.read(str(path))
    assert [r["_line"] for r in rows] == [2, 4]
