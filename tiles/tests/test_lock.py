"""tiles/lock.sh: reading and rewriting the `KEY=value` lines of a lock file
(tiles/sources.lock, web/tiles.lock).

Runs the shell functions through a real subshell (`source lock.sh; ...`),
like test_fetch.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

LOCK_SH = Path(__file__).resolve().parent.parent / "lock.sh"

LOCK = """\
# The tile archive the website ships.
ARCHIVE_URL=https://example.org/old.pmtiles
ARCHIVE_SHA256=aaaa
"""


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Source lock.sh, then call the named function with the given args."""
    return subprocess.run(
        ["bash", "-c", f'source "{LOCK_SH}" && "$@"', "bash", *args],
        capture_output=True,
        encoding="utf-8",
    )


def lock_file(tmp_path: Path) -> Path:
    lock = tmp_path / "tiles.lock"
    lock.write_text(LOCK, encoding="utf-8")
    return lock


# ----------------------------------------------------------------- lock_get ---
def test_lock_get_prints_the_value_of_a_key(tmp_path: Path) -> None:
    result = run("lock_get", str(lock_file(tmp_path)), "ARCHIVE_SHA256")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "aaaa\n"


def test_lock_get_names_the_key_and_the_file_it_is_missing_from(tmp_path: Path) -> None:
    lock = lock_file(tmp_path)

    result = run("lock_get", str(lock), "PLANETILER_URL")

    assert result.returncode != 0
    assert f"{lock} has no PLANETILER_URL=" in result.stderr


# ----------------------------------------------------------------- lock_set ---
def test_lock_set_rewrites_only_the_line_of_its_key(tmp_path: Path) -> None:
    lock = lock_file(tmp_path)

    result = run("lock_set", str(lock), "ARCHIVE_SHA256", "bbbb")

    assert result.returncode == 0, result.stderr
    assert lock.read_text(encoding="utf-8") == LOCK.replace(
        "ARCHIVE_SHA256=aaaa", "ARCHIVE_SHA256=bbbb"
    )


def test_lock_set_writes_a_url_as_it_is(tmp_path: Path) -> None:
    lock = lock_file(tmp_path)
    url = r"https://example.org/a/b.pmtiles?x=1&y=\2|z"

    run("lock_set", str(lock), "ARCHIVE_URL", url)

    assert f"ARCHIVE_URL={url}\n" in lock.read_text(encoding="utf-8")


def test_lock_set_leaves_a_lock_without_the_key_alone(tmp_path: Path) -> None:
    lock = lock_file(tmp_path)

    result = run("lock_set", str(lock), "ARCHIVE_NAME", "sh.pmtiles")

    assert result.returncode != 0
    assert f"{lock} has no ARCHIVE_NAME=" in result.stderr
    assert lock.read_text(encoding="utf-8") == LOCK
