"""Reading the hand-edited CSV files and writing any file safely.

The inputs are edited by hand, some in a spreadsheet, so reading them has to
cope with what a spreadsheet saves (a byte order mark, a `;`-separated
export); and the outputs -- the name list above all, which holds uncommitted
hand edits -- must never be left half-written."""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from collections.abc import Iterator, Sequence
from typing import IO, Literal, overload

from frasch.errors import Conflict


# ---------------------------------------------------------------- reading ---
def open_csv(path: str) -> IO[str]:
    """Open one of the hand-edited CSV files for reading.  A spreadsheet's
    "CSV UTF-8" starts it with a byte order mark, which would otherwise end up
    in the first column's name."""
    return open(path, encoding="utf-8-sig", newline="")


def decode(data: bytes) -> str:
    """`open_csv` for a file already read as bytes."""
    return data.decode("utf-8-sig")


SEMICOLON_SEPARATED = (
    "the cells are separated by `;`, not `,` (a German-locale "
    "spreadsheet export?) -- save it as comma-separated CSV"
)


def csv_header_problem(fields: Sequence[str], required: Sequence[str]) -> str | None:
    """What makes a CSV header unreadable -- a `;`-separated export, a column
    named twice, a missing one -- or None."""
    if len(fields) == 1 and ";" in fields[0]:
        return SEMICOLON_SEPARATED
    twice = sorted({c for c in fields if fields.count(c) > 1})
    if twice:
        return f"column(s) named twice: {', '.join(twice)}"
    missing = [c for c in required if c not in fields]
    if missing:
        return f"missing column(s) {', '.join(missing)}"
    return None


def cell_count_problem(cells: Sequence[str], header: Sequence[str]) -> str | None:
    """A row whose cells do not line up with the header's columns: a comma
    too many or too few, and every cell after it is in the wrong column."""
    if len(cells) != len(header):
        return f"{len(cells)} cells, the header has {len(header)} (a comma too many or too few?)"
    return None


# ---------------------------------------------------------------- writing ---
MISSING = "missing"  # `expect` for a file that must not exist


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(path: str) -> str:
    """The sha256 of a file's bytes, or MISSING -- what `atomic_write`
    compares against to notice a concurrent change."""
    try:
        with open(path, "rb") as fh:
            return digest(fh.read())
    except FileNotFoundError:
        return MISSING


def atomic_write(path: str, data: bytes | str, expect: str | None = None) -> None:
    """Replace `path` with `data` in one step (see `replacing`).

    `expect` (a `fingerprint`) makes it refuse -- with `Conflict`, leaving the
    file alone -- when the file no longer is what the caller read."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    with replacing(path, expect) as fh:
        fh.write(data)


@overload
def replacing(
    path: str, expect: str | None = None, text: Literal[False] = False
) -> contextlib.AbstractContextManager[IO[bytes]]: ...
@overload
def replacing(
    path: str, expect: str | None = None, *, text: Literal[True]
) -> contextlib.AbstractContextManager[IO[str]]: ...
def replacing(
    path: str, expect: str | None = None, text: bool = False
) -> contextlib.AbstractContextManager[IO[bytes] | IO[str]]:
    """A file handle whose content replaces `path` in one step when the block
    ends: it writes a temporary file next to it, flushes it to disk, then
    `os.replace`s it over the original.  A crash at any point -- or an
    exception in the block -- leaves either the old or the new file, never
    half of one (a half-written JSON-lines file that ends at a line boundary
    looks complete).  `text` opens it as UTF-8 text instead of bytes, for
    files streamed line by line; `expect` as in `atomic_write`."""
    return _replacing(path, expect, text)


@contextlib.contextmanager
def _replacing(path: str, expect: str | None, text: bool) -> Iterator[IO[bytes] | IO[str]]:
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp")
    try:
        fh: IO[bytes] | IO[str]
        with os.fdopen(fd, "w", encoding="utf-8") if text else os.fdopen(fd, "wb") as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, _mode_for(path))
        if expect is not None and fingerprint(path) != expect:
            raise Conflict(
                f"{path} changed on disk while this was running "
                f"(a spreadsheet, `frasch match` or `frasch curate apply`?) -- "
                f"not overwriting it.  Nothing was written; save or "
                f"commit the other change and run this again."
            )
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    _sync_directory(directory)  # make the rename itself durable


def _mode_for(path: str) -> int:
    """The permissions the replacement gets: the original's, else what a
    plain `open` would have created."""
    try:
        return os.stat(path).st_mode & 0o7777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def _sync_directory(directory: str) -> None:
    with contextlib.suppress(OSError):
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
