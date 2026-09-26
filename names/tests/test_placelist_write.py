"""places.csv is written atomically and only over what was read (#21, M1)."""
from __future__ import annotations

import csv
import os

import pytest

import placelist
from conftest import places_text

ROWS = [
    {"kind": "settlement", "mooring": f"Taarep {i}", "de": f"Dorf {i}"}
    for i in range(20)
]


@pytest.fixture
def places(world):
    path = world / "places.csv"
    path.write_text(places_text(ROWS), encoding="utf-8")
    return path


def test_round_trip_is_byte_identical(places):
    before = places.read_bytes()
    rows, fields = placelist.read(str(places))
    placelist.write(rows, str(places), fields)
    assert places.read_bytes() == before


def test_interrupted_write_leaves_the_file_alone(places, monkeypatch):
    before = places.read_bytes()
    rows, fields = placelist.read(str(places))
    rows[0]["mooring"] = "changed"

    class Crashing(csv.DictWriter):
        written = 0

        def writerow(self, row):
            Crashing.written += 1
            if Crashing.written > 5:
                raise KeyboardInterrupt("Ctrl-C half-way")
            return super().writerow(row)

    monkeypatch.setattr(placelist.csv, "DictWriter", Crashing)
    with pytest.raises(KeyboardInterrupt):
        placelist.write(rows, str(places), fields)
    assert places.read_bytes() == before
    assert sorted(os.listdir(places.parent)) == ["curation.csv", "places.csv", "work"]


def test_crash_while_flushing_leaves_the_file_alone(places, monkeypatch):
    before = places.read_bytes()
    rows, fields = placelist.read(str(places))
    rows[0]["mooring"] = "changed"

    def boom(fd):
        raise OSError("disk full")

    monkeypatch.setattr(placelist.os, "fsync", boom)
    with pytest.raises(OSError):
        placelist.write(rows, str(places), fields)
    assert places.read_bytes() == before
    assert sorted(os.listdir(places.parent)) == ["curation.csv", "places.csv", "work"]


def test_refuses_to_overwrite_a_concurrent_change(places):
    rows, fields = placelist.read(str(places))
    rows[0]["mooring"] = "mine"
    # a spreadsheet saves the file while the script is busy
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])
    places.write_text(theirs, encoding="utf-8")
    with pytest.raises(placelist.Conflict):
        placelist.write(rows, str(places), fields)
    assert places.read_text(encoding="utf-8") == theirs


def test_write_without_read_is_an_error(world):
    path = world / "never-read.csv"
    with pytest.raises(RuntimeError):
        placelist.write([], str(path))
    assert not path.exists()


def test_write_keeps_the_file_mode(places):
    os.chmod(places, 0o640)
    rows, fields = placelist.read(str(places))
    placelist.write(rows, str(places), fields)
    assert os.stat(places).st_mode & 0o777 == 0o640


def test_second_write_in_one_run_is_allowed(places):
    rows, fields = placelist.read(str(places))
    rows[0]["mooring"] = "one"
    placelist.write(rows, str(places), fields)
    rows[0]["mooring"] = "two"
    placelist.write(rows, str(places), fields)
    assert placelist.read(str(places))[0][0]["mooring"] == "two"


def test_lock_is_exclusive(places):
    with placelist.lock(str(places)):
        with pytest.raises(SystemExit, match="another match.py"):
            with placelist.lock(str(places)):
                pass
    with placelist.lock(str(places)):   # released again
        pass
