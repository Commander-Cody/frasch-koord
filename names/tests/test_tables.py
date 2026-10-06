"""tables.py: the one reader and writer of the hand-edited CSV tables (#92)."""

from __future__ import annotations

from pathlib import Path

from frasch import tables
from frasch.errors import Problem


def table_file(tmp_path: Path, text: str) -> str:
    path = tmp_path / "table.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_the_header_and_each_row_with_its_line(tmp_path: Path) -> None:
    table = tables.read_table(table_file(tmp_path, "tag,label\nfrr-x-mooring,Mooring\n"))
    assert table.header == ["tag", "label"]
    assert table.rows == [(2, ["frr-x-mooring", "Mooring"])]


def test_a_semicolon_separated_export_is_one_problem_on_the_header(tmp_path: Path) -> None:
    # A German-locale spreadsheet saves "CSV" with `;` between the cells.
    path = table_file(tmp_path, "tag;label\nfrr-x-mooring;Mooring\n")
    table = tables.read_table(path, ["tag", "label"])
    assert table.problems == [
        Problem(
            path,
            1,
            "the cells are separated by `;`, not `,` (a German-locale "
            "spreadsheet export?) -- save it as comma-separated CSV",
        )
    ]


def test_a_row_with_the_wrong_number_of_cells_is_a_problem_not_a_row(tmp_path: Path) -> None:
    # One comma too few and every later cell would sit one column to the left.
    path = table_file(tmp_path, "tag,label,note\nfrr-x-mooring,Mooring\nfrr-x-fering,Fering,\n")
    table = tables.read_table(path)
    assert table.problems == [
        Problem(path, 2, "2 cells, the header has 3 (a comma too many or too few?)")
    ]
    assert table.rows == [(3, ["frr-x-fering", "Fering", ""])]


def test_a_problem_after_a_blank_line_is_on_the_line_an_editor_sees(tmp_path: Path) -> None:
    # The blank line is no row and no problem, but it counts.
    path = table_file(tmp_path, "tag,label\nfrr-x-mooring,Mooring\n\nfrr-x-fering\n")
    table = tables.read_table(path)
    assert [p.line for p in table.problems] == [4]


def test_a_byte_order_mark_is_not_part_of_the_first_column_name(tmp_path: Path) -> None:
    # A spreadsheet's "CSV UTF-8" starts the file with one.
    table = tables.read_table(table_file(tmp_path, "﻿tag,label\n"))
    assert table.header == ["tag", "label"]


def test_a_column_named_twice_is_a_problem_on_the_header(tmp_path: Path) -> None:
    # Read by name, one of the two would be dropped without a word.
    path = table_file(tmp_path, "tag,label,tag\n")
    assert tables.read_table(path).problems == [Problem(path, 1, "column(s) named twice: tag")]


def test_a_missing_required_column_is_a_problem_on_the_header(tmp_path: Path) -> None:
    path = table_file(tmp_path, "tag,note\n")
    table = tables.read_table(path, ["tag", "label", "status"])
    assert table.problems == [Problem(path, 1, "missing column(s) label, status")]


def test_the_digest_is_that_of_the_files_bytes(tmp_path: Path) -> None:
    # What a writer compares against to notice that someone else saved the file.
    table = tables.read_table(table_file(tmp_path, "tag\n"))
    assert table.digest == "ccda8f9a2cb0295182b9a99e4c8270badcc89525850e1e737a294fb426363ac9"


def test_the_records_are_the_rows_by_column_with_their_cells_stripped(tmp_path: Path) -> None:
    table = tables.read_table(table_file(tmp_path, "tag,label\nfrr-x-mooring, Mooring \n"))
    assert list(table.records()) == [(2, {"tag": "frr-x-mooring", "label": "Mooring"})]


def test_writes_the_header_and_each_row_in_the_order_of_the_fields() -> None:
    written = tables.write_rows(["osm", "name"], [{"name": "Habel", "osm": "way/177387348"}])
    assert written == b"osm,name\nway/177387348,Habel\n"


def test_a_row_is_written_in_the_fields_only() -> None:
    # A cell the row lacks is empty; what it has beyond the fields is left out.
    written = tables.write_rows(["osm", "name"], [{"osm": "way/177387348", "line": "2"}])
    assert written == b"osm,name\nway/177387348,\n"


def test_rows_to_append_to_a_file_are_written_without_a_header() -> None:
    written = tables.write_rows(["osm", "name"], [{"osm": "way/1"}], header=False)
    assert written == b"way/1,\n"
