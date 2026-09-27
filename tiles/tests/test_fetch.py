"""tiles/fetch.sh: the download-and-verify helper build.sh sources.

Runs the shell functions through a real subshell (`source fetch.sh; ...`)
against file:// URLs, so curl's own request/response handling is exercised
too -- these are not tests of the script text."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

FETCH_SH = Path(__file__).resolve().parent.parent / "fetch.sh"


def run(*args: str) -> subprocess.CompletedProcess:
    """Source fetch.sh, then call the named function with the given args --
    exactly what build.sh does after `source ./fetch.sh`."""
    return subprocess.run(
        ["bash", "-c", f'source "{FETCH_SH}" && "$@"', "bash", *args],
        capture_output=True, text=True,
    )


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_of(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ----------------------------------------------------------- fetch_verified ---
def test_accepts_a_good_file_with_the_right_checksum(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"planetiler jar contents\n")
    dest = tmp_path / "out.bin"

    result = run("fetch_verified", src.as_uri(), str(dest), "sha256", sha256_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == src.read_bytes()
    assert not Path(str(dest) + ".part").exists()



def test_a_binary_file_passes_without_a_word(tmp_path):
    # an OSM PBF starts with a zero byte (the length of its first block)
    src = tmp_path / "src.osm.pbf"
    src.write_bytes(b"\x00\x00\x00\x0d\x0a\x09OSMHeader\x18")
    dest = tmp_path / "out.osm.pbf"

    result = run("fetch_verified", src.as_uri(), str(dest), "md5", md5_of(src.read_bytes()))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""

def test_rejects_a_wrong_checksum(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"planetiler jar contents\n")
    dest = tmp_path / "out.bin"

    result = run("fetch_verified", src.as_uri(), str(dest), "sha256", "0" * 64)

    assert result.returncode != 0
    assert result.stderr.strip() != ""
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


def test_rejects_an_html_response(tmp_path):
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


def test_leaves_no_part_file_when_the_url_does_not_resolve(tmp_path):
    dest = tmp_path / "out.bin"

    result = run("fetch_verified", (tmp_path / "missing.bin").as_uri(), str(dest), "sha256", "0" * 64)

    assert result.returncode != 0
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()


# ------------------------------------------------------- fetch_geofabrik_verified ---
def test_geofabrik_variant_verifies_against_the_md5_sidecar(tmp_path):
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_text(f"{md5_of(pbf.read_bytes())}  region-latest.osm.pbf\n")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == pbf.read_bytes()


def test_geofabrik_variant_rejects_an_html_md5_file(tmp_path):
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_bytes(b"<html><body>Not Found</body></html>")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode != 0
    assert not dest.exists()


def test_geofabrik_variant_rejects_an_unparsable_md5_file(tmp_path):
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_text("not a checksum line\n")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode != 0
    assert not dest.exists()


def test_geofabrik_variant_rejects_a_wrong_md5(tmp_path):
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_text("0" * 32 + "  region-latest.osm.pbf\n")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode != 0
    assert not dest.exists()


# --------------------------------------------------- geofabrik_path / region_stem ---
def test_geofabrik_path_expands_a_bare_name_under_germany():
    result = run("geofabrik_path", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/germany/schleswig-holstein"


def test_geofabrik_path_keeps_a_full_path_as_is():
    result = run("geofabrik_path", "europe/denmark")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/denmark"


def test_geofabrik_path_keeps_a_deeper_full_path_as_is():
    result = run("geofabrik_path", "europe/germany/schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/germany/schleswig-holstein"


def test_geofabrik_path_rejects_shell_metacharacters():
    result = run("geofabrik_path", "europe/denmark; rm -rf /")
    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_geofabrik_path_rejects_path_traversal():
    result = run("geofabrik_path", "../../etc/passwd")
    assert result.returncode != 0


def test_region_stem_is_the_last_path_component():
    result = run("region_stem", "europe/germany/schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein"


def test_region_stem_of_a_bare_name_is_itself():
    result = run("region_stem", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein"


def test_region_stem_rejects_an_invalid_region():
    result = run("region_stem", "Europe/Denmark")
    assert result.returncode != 0
