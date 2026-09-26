"""`placelist.read` takes what a spreadsheet saves (#22, M3)."""
from __future__ import annotations

import pytest

import placelist
from conftest import places_text

TOFTUM = {"kind": "settlement", "mooring": "Toftem", "de": "Toftum",
          "osm": "node/240044107", "status": "ok"}


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
