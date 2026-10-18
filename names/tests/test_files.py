"""files.py: the lock a read-modify-write run of the name list holds, and
the atomic write.  How a write survives a crash, refuses a concurrent change
and keeps the file's mode is tested through placelist.write
(test_placelist_write.py)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from frasch import files
from frasch.errors import Conflict, PipelineError
from frasch.paths import Workspace


def test_lock_is_exclusive(ws: Workspace) -> None:
    with files.lock(ws.lock):
        with pytest.raises(PipelineError, match="another `frasch match`"):
            with files.lock(ws.lock):
                pass
    with files.lock(ws.lock):  # released again
        pass


def test_a_file_expected_missing_is_written(tmp_path: Path) -> None:
    path = tmp_path / "new.csv"
    files.atomic_write(str(path), "a\n", expect=files.MISSING)
    assert path.read_bytes() == b"a\n"


def test_a_file_expected_missing_that_is_there_is_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "new.csv"
    path.write_bytes(b"someone else's\n")
    with pytest.raises(Conflict):
        files.atomic_write(str(path), "a\n", expect=files.MISSING)
    assert path.read_bytes() == b"someone else's\n"


def test_text_is_written_as_utf8(tmp_path: Path) -> None:
    path = tmp_path / "names.jsonl"
    with files.replacing(str(path), text=True) as fh:
        fh.write("Schörkewärw\n")
    assert path.read_bytes() == "Schörkewärw\n".encode()


@pytest.fixture
def umask() -> Iterator[int]:
    """A umask of 027 for the test, the previous one restored after it."""
    previous = os.umask(0o027)
    yield 0o027
    os.umask(previous)


def test_a_new_file_gets_the_mode_a_plain_open_would_give_it(tmp_path: Path, umask: int) -> None:
    path = tmp_path / "new.csv"
    files.atomic_write(str(path), "a\n")
    assert path.stat().st_mode & 0o777 == 0o640
