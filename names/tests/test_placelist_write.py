"""places.csv is written atomically and only over what was read (#21, M1)."""

from __future__ import annotations

import csv
import os
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from frasch import errors, placelist
from conftest import REGISTRY, places_text

ROWS = [{"kind": "settlement", "mooring": f"Taarep {i}", "de": f"Dorf {i}"} for i in range(20)]


@pytest.fixture
def places(world: Path) -> Path:
    path = world / "places.csv"
    path.write_text(places_text(ROWS), encoding="utf-8")
    return path


def test_round_trip_is_byte_identical(places: Path) -> None:
    before = places.read_bytes()
    placelist.read(str(places), REGISTRY).write()
    assert places.read_bytes() == before


def test_cells_that_need_quotes_and_an_editors_own_column_round_trip_byte_identical(
    world: Path,
) -> None:
    # the guarantee that the matcher and the curation only ever touch the
    # cells they mean to; the quoting is spelled out, as an editor saves it
    columns = [*placelist.columns(REGISTRY), "mine"]

    def line(**cells: str) -> str:
        return ",".join(cells.get(c, "") for c in columns) + "\n"

    path = world / "places.csv"
    path.write_text(
        ",".join(columns)
        + "\n"
        + line(kind="settlement", mooring="Taarep", de="Dorf", note='"a ""b"", c"', id="taarep")
        + line(kind="warft", solring="Wärw; Werw (old)", note='"one\ntwo"', id="warw", mine="x"),
        encoding="utf-8",
    )
    before = path.read_bytes()
    placelist.read(str(path), REGISTRY).write()
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "edit, line",
    [
        (lambda text: "\ufeff" + text, 1),  # Excel's "CSV UTF-8"
        (lambda text: text.replace("\n", "\r\n"), 1),
        (lambda text: text.replace("Dorf 1", '"Dorf 1"'), 3),
        (lambda text: text.replace("Dorf 1", "Dorf 1 "), 3),
        (lambda text: text.replace("\nsettlement,Taarep 1,", "\n\nsettlement,Taarep 1,"), 3),
    ],
    ids=["byte order mark", "windows line ends", "quoted cell", "spaces in a cell", "blank line"],
)
def test_a_list_not_in_the_written_form_differs_from_it_at_its_first_such_line(
    world: Path, edit: Callable[[str], str], line: int
) -> None:
    # the next write by the matcher or the curation would change more than
    # the cells it means to
    path = world / "places.csv"
    path.write_bytes(edit(places_text(ROWS[:2])).encode())
    problem = placelist.form_problem(placelist.table(str(path)))
    assert problem is not None and problem.line == line


def test_a_list_in_the_written_form_has_no_form_problem(places: Path) -> None:
    assert placelist.form_problem(placelist.table(str(places))) is None


def test_interrupted_write_leaves_the_file_alone(
    places: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = places.read_bytes()
    names = placelist.read(str(places), REGISTRY)
    names.rows[0]["mooring"] = "changed"

    class Crashing(csv.DictWriter[str]):
        written = 0

        def writerow(self, row: Mapping[str, object]) -> object:
            Crashing.written += 1
            if Crashing.written > 5:
                raise KeyboardInterrupt("Ctrl-C half-way")
            return super().writerow(row)

    monkeypatch.setattr("frasch.tables.csv.DictWriter", Crashing)
    with pytest.raises(KeyboardInterrupt):
        names.write()
    assert places.read_bytes() == before
    assert sorted(os.listdir(places.parent)) == [
        "curation.csv",
        "dialect_areas.csv",
        "dialects.csv",
        "places.csv",
        "work",
    ]


def test_crash_while_flushing_leaves_the_file_alone(
    places: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = places.read_bytes()
    names = placelist.read(str(places), REGISTRY)
    names.rows[0]["mooring"] = "changed"

    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        names.write()
    assert places.read_bytes() == before
    assert sorted(os.listdir(places.parent)) == [
        "curation.csv",
        "dialect_areas.csv",
        "dialects.csv",
        "places.csv",
        "work",
    ]


def test_refuses_to_overwrite_a_concurrent_change(places: Path) -> None:
    names = placelist.read(str(places), REGISTRY)
    names.rows[0]["mooring"] = "mine"
    # a spreadsheet saves the file while the script is busy
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])
    places.write_text(theirs, encoding="utf-8")
    with pytest.raises(errors.Conflict):
        names.write()
    assert places.read_text(encoding="utf-8") == theirs


def test_a_list_read_before_another_run_wrote_does_not_overwrite_it(places: Path) -> None:
    mine = placelist.read(str(places), REGISTRY)
    theirs = placelist.read(str(places), REGISTRY)
    theirs.rows[0]["mooring"] = "theirs"
    theirs.write()
    mine.rows[1]["mooring"] = "mine"
    with pytest.raises(errors.Conflict):
        mine.write()


def test_write_keeps_the_file_mode(places: Path) -> None:
    os.chmod(places, 0o640)
    placelist.read(str(places), REGISTRY).write()
    assert os.stat(places).st_mode & 0o777 == 0o640


def test_second_write_in_one_run_is_allowed(places: Path) -> None:
    names = placelist.read(str(places), REGISTRY)
    names.rows[0]["mooring"] = "one"
    names.write()
    names.rows[0]["mooring"] = "two"
    names.write()
    assert placelist.read(str(places), REGISTRY).rows[0]["mooring"] == "two"
