"""Writing any file safely.

The outputs -- the name list above all, which holds uncommitted hand edits --
must never be left half-written, a file someone else saved in the meantime
must not be overwritten, and two runs that read, change and write the name
list must not overlap (`lock`)."""

from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import tempfile
from collections.abc import Iterator
from typing import IO, Literal, overload

from frasch.errors import Conflict, PipelineError


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


@contextlib.contextmanager
def lock(lock_path: str) -> Iterator[None]:
    """Hold the workspace's lock file for the duration of a read-modify-write
    run, so that `frasch match` and `frasch curate apply` never run at the
    same time.  Advisory (`flock`): a spreadsheet does not take it -- that is
    what the check in `atomic_write` is for."""
    import fcntl  # POSIX only; the pipeline runs in WSL

    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    with open(lock_path, "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise
            raise PipelineError(
                f"{lock_path} is held: another `frasch match` or "
                f"`frasch curate apply` is running -- wait for it to "
                f"finish"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
