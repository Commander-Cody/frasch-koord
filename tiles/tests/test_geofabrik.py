"""tiles/geofabrik.sh: the names, URLs and verified downloads of Geofabrik's
extracts, which build.sh and `just extracts` source.

Runs the shell functions through a real subshell (`source geofabrik.sh;
...`) against file:// URLs, like test_fetch.py."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

GEOFABRIK_SH = Path(__file__).resolve().parent.parent / "geofabrik.sh"
# what the functions read from the environment, set by each test alone
OWN_ENV = ("GEOFABRIK_URL", "REFRESH")


def run(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Source geofabrik.sh, then call the named function with the given args,
    with `env` added to the environment."""
    return subprocess.run(
        ["bash", "-c", f'source "{GEOFABRIK_SH}" && "$@"', "bash", *args],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k not in OWN_ENV} | env,
    )


def md5_of(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ------------------------------------------------------- fetch_geofabrik_verified ---
def test_geofabrik_variant_verifies_against_the_md5_sidecar(tmp_path: Path) -> None:
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_text(f"{md5_of(pbf.read_bytes())}  region-latest.osm.pbf\n")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == pbf.read_bytes()


def test_geofabrik_variant_rejects_an_html_md5_file(tmp_path: Path) -> None:
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_bytes(b"<html><body>Not Found</body></html>")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode != 0
    assert not dest.exists()


def test_geofabrik_variant_rejects_an_unparsable_md5_file(tmp_path: Path) -> None:
    pbf = tmp_path / "region-latest.osm.pbf"
    pbf.write_bytes(b"fake extract data\n")
    md5_file = tmp_path / "region-latest.osm.pbf.md5"
    md5_file.write_text("not a checksum line\n")
    dest = tmp_path / "data" / "region-latest.osm.pbf"
    dest.parent.mkdir()

    result = run("fetch_geofabrik_verified", pbf.as_uri(), str(dest))

    assert result.returncode != 0
    assert not dest.exists()


def test_geofabrik_variant_rejects_a_wrong_md5(tmp_path: Path) -> None:
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
def test_geofabrik_path_expands_a_bare_name_under_germany() -> None:
    result = run("geofabrik_path", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/germany/schleswig-holstein"


def test_geofabrik_path_keeps_a_full_path_as_is() -> None:
    result = run("geofabrik_path", "europe/denmark")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/denmark"


def test_geofabrik_path_keeps_a_deeper_full_path_as_is() -> None:
    result = run("geofabrik_path", "europe/germany/schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "europe/germany/schleswig-holstein"


def test_geofabrik_path_rejects_shell_metacharacters() -> None:
    result = run("geofabrik_path", "europe/denmark; rm -rf /")
    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_geofabrik_path_rejects_path_traversal() -> None:
    result = run("geofabrik_path", "../../etc/passwd")
    assert result.returncode != 0


def test_region_stem_is_the_last_path_component() -> None:
    result = run("region_stem", "europe/germany/schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein"


def test_region_stem_of_a_bare_name_is_itself() -> None:
    result = run("region_stem", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein"


def test_region_stem_rejects_an_invalid_region() -> None:
    result = run("region_stem", "Europe/Denmark")
    assert result.returncode != 0


# -------------------------------------- geofabrik_extract_name / _url (snapshot) ---
def test_extract_name_without_a_snapshot_is_the_latest_file() -> None:
    result = run("geofabrik_extract_name", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein-latest.osm.pbf"


def test_extract_name_with_a_snapshot_is_the_dated_file() -> None:
    result = run("geofabrik_extract_name", "schleswig-holstein", "260923")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "schleswig-holstein-260923.osm.pbf"


def test_extract_name_takes_the_stem_of_a_full_path_region() -> None:
    result = run("geofabrik_extract_name", "europe/denmark", "260923")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "denmark-260923.osm.pbf"


def test_extract_name_rejects_a_malformed_snapshot() -> None:
    for snapshot in ("2609", "26-09-23", "../x", "2609233", "latest"):
        result = run("geofabrik_extract_name", "schleswig-holstein", snapshot)
        assert result.returncode != 0, snapshot
        assert result.stdout.strip() == "", snapshot
        assert "invalid snapshot" in result.stderr, snapshot


def test_extract_url_is_the_geofabrik_download_of_the_latest_file() -> None:
    result = run("geofabrik_extract_url", "schleswig-holstein")
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        == "https://download.geofabrik.de/europe/germany/schleswig-holstein-latest.osm.pbf"
    )


def test_extract_url_with_a_snapshot_names_the_dated_file() -> None:
    result = run("geofabrik_extract_url", "europe/denmark", "260923")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://download.geofabrik.de/europe/denmark-260923.osm.pbf"


def test_extract_url_is_on_the_server_geofabrik_url_names() -> None:
    result = run("geofabrik_extract_url", "europe/denmark", GEOFABRIK_URL="file:///mirror")
    assert result.stdout.strip() == "file:///mirror/europe/denmark-latest.osm.pbf"


def test_extract_url_rejects_a_malformed_snapshot() -> None:
    result = run("geofabrik_extract_url", "schleswig-holstein", "../x")
    assert result.returncode != 0
    assert result.stdout.strip() == ""


# ------------------------------------------------------- fetch_geofabrik_extract ---
def mirror(tmp_path: Path, name: str, data: bytes) -> str:
    """A Geofabrik stand-in at tmp_path/mirror holding the Denmark extract
    `name` and its MD5 sidecar; its URL, for GEOFABRIK_URL."""
    europe = tmp_path / "mirror" / "europe"
    europe.mkdir(parents=True)
    (europe / name).write_bytes(data)
    (europe / f"{name}.md5").write_text(f"{md5_of(data)}  {name}\n")
    return (tmp_path / "mirror").as_uri()


def test_a_missing_extract_is_downloaded_into_the_directory(tmp_path: Path) -> None:
    url = mirror(tmp_path, "denmark-latest.osm.pbf", b"extract\n")

    result = run(
        "fetch_geofabrik_extract", "europe/denmark", str(tmp_path / "data"), GEOFABRIK_URL=url
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "denmark-latest.osm.pbf").read_bytes() == b"extract\n"


def test_a_snapshot_downloads_the_dated_extract(tmp_path: Path) -> None:
    url = mirror(tmp_path, "denmark-260923.osm.pbf", b"extract of 23 Sep\n")

    result = run(
        "fetch_geofabrik_extract", "europe/denmark", str(tmp_path), "260923", GEOFABRIK_URL=url
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "denmark-260923.osm.pbf").read_bytes() == b"extract of 23 Sep\n"


def test_an_extract_already_there_is_kept(tmp_path: Path) -> None:
    url = mirror(tmp_path, "denmark-latest.osm.pbf", b"newer extract\n")
    (tmp_path / "denmark-latest.osm.pbf").write_bytes(b"older extract\n")

    result = run("fetch_geofabrik_extract", "europe/denmark", str(tmp_path), GEOFABRIK_URL=url)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "denmark-latest.osm.pbf").read_bytes() == b"older extract\n"


def test_refresh_downloads_an_extract_already_there_again(tmp_path: Path) -> None:
    url = mirror(tmp_path, "denmark-latest.osm.pbf", b"newer extract\n")
    (tmp_path / "denmark-latest.osm.pbf").write_bytes(b"older extract\n")

    result = run(
        "fetch_geofabrik_extract", "europe/denmark", str(tmp_path), GEOFABRIK_URL=url, REFRESH="1"
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "denmark-latest.osm.pbf").read_bytes() == b"newer extract\n"
