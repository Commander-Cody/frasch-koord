"""tiles/fetch.sh: the download-and-verify helper build.sh and geofabrik.sh source.

Runs the shell functions through a real subshell (`source fetch.sh; ...`)
against file:// URLs, so curl's own request/response handling is exercised
too -- these are not tests of the script text."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

FETCH_SH = Path(__file__).resolve().parent.parent / "fetch.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Source fetch.sh, then call the named function with the given args --
    exactly what build.sh does after `source ./fetch.sh`."""
    return subprocess.run(
        ["bash", "-c", f'source "{FETCH_SH}" && "$@"', "bash", *args],
        capture_output=True,
        encoding="utf-8",
    )


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_of(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ----------------------------------------------------------- fetch_verified ---
def test_accepts_a_good_file_with_the_right_checksum(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"planetiler jar contents\n")
    dest = tmp_path / "out.bin"

    result = run("fetch_verified", src.as_uri(), str(dest), "sha256", sha256_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == src.read_bytes()
    assert not Path(str(dest) + ".part").exists()


def test_a_binary_file_passes_without_a_word(tmp_path: Path) -> None:
    # an OSM PBF starts with a zero byte (the length of its first block)
    src = tmp_path / "src.osm.pbf"
    src.write_bytes(b"\x00\x00\x00\x0d\x0a\x09OSMHeader\x18")
    dest = tmp_path / "out.osm.pbf"

    result = run("fetch_verified", src.as_uri(), str(dest), "md5", md5_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_rejects_a_wrong_checksum(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"planetiler jar contents\n")
    dest = tmp_path / "out.bin"

    result = run("fetch_verified", src.as_uri(), str(dest), "sha256", "0" * 64)

    assert result.returncode != 0
    assert result.stderr.strip() != ""
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_rejects_an_html_response(tmp_path: Path) -> None:
    # Geofabrik's stand-in for "wrong path": 200/302 with an HTML body, which
    # curl --fail alone does not treat as an error.
    src = tmp_path / "notfound.html"
    body = b"<html><body>Not Found</body></html>"
    src.write_bytes(body)
    dest = tmp_path / "out.bin"

    # Even a checksum that matches the (wrong) content must not save it --
    # the content-sniff has to run regardless of what hash was expected.
    result = run("fetch_verified", src.as_uri(), str(dest), "sha256", sha256_of(body))

    assert result.returncode != 0
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_leaves_no_part_file_when_the_url_does_not_resolve(tmp_path: Path) -> None:
    dest = tmp_path / "out.bin"

    result = run(
        "fetch_verified", (tmp_path / "missing.bin").as_uri(), str(dest), "sha256", "0" * 64
    )

    assert result.returncode != 0
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


# ------------------------------------------------------------- fetch_pinned ---
def test_pinned_fetch_downloads_a_missing_file(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    src.write_bytes(b"natural earth\n")
    dest = tmp_path / "sources" / "ne.zip"
    dest.parent.mkdir()

    result = run("fetch_pinned", src.as_uri(), str(dest), sha256_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == b"natural earth\n"


def test_pinned_fetch_leaves_a_matching_file_alone(tmp_path: Path) -> None:
    dest = tmp_path / "ne.zip"
    dest.write_bytes(b"natural earth\n")

    # the source does not even exist: a matching file is not fetched again
    result = run(
        "fetch_pinned", (tmp_path / "gone.zip").as_uri(), str(dest), sha256_of(b"natural earth\n")
    )

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == b"natural earth\n"


def test_pinned_fetch_replaces_a_file_with_the_wrong_checksum(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    src.write_bytes(b"natural earth\n")
    dest = tmp_path / "ne.zip"
    dest.write_bytes(b"half a downloa")

    result = run("fetch_pinned", src.as_uri(), str(dest), sha256_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == b"natural earth\n"


def test_pinned_fetch_fails_on_a_mismatching_download_and_leaves_nothing(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    src.write_bytes(b"something else\n")
    dest = tmp_path / "ne.zip"

    result = run("fetch_pinned", src.as_uri(), str(dest), sha256_of(b"natural earth\n"))

    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_pinned_fetch_creates_the_destination_directory(tmp_path: Path) -> None:
    src = tmp_path / "src.zip"
    src.write_bytes(b"natural earth\n")
    dest = tmp_path / "data" / "sources" / "ne.zip"

    result = run("fetch_pinned", src.as_uri(), str(dest), sha256_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == b"natural earth\n"


# -------------------------------------------------------------- checksum_of ---
def test_checksum_of_prints_a_files_sha256(tmp_path: Path) -> None:
    file = tmp_path / "archive.pmtiles"
    file.write_bytes(b"abc")

    result = run("checksum_of", "sha256", str(file))

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\n"


def test_checksum_of_rejects_an_unknown_algorithm(tmp_path: Path) -> None:
    file = tmp_path / "archive.pmtiles"
    file.write_bytes(b"abc")

    result = run("checksum_of", "crc32", str(file))

    assert result.returncode != 0
    assert "unsupported checksum algorithm: crc32" in result.stderr
