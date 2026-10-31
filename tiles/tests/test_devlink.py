"""tiles/devlink.sh: linking a freshly built archive for the dev server, under
the name web/tiles.lock pins, since the dev server serves only that one.

Runs the shell function through a real subshell, like test_lock.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

DEVLINK_SH = Path(__file__).resolve().parent.parent / "devlink.sh"

LOCK = """\
ARCHIVE_URL=https://example.org/releases/schleswig-holstein.pmtiles
ARCHIVE_SHA256=aaaa
"""


def link_dev_archive(tmp_path: Path, archive: str) -> subprocess.CompletedProcess[str]:
    """Run link_dev_archive with a lock pinning schleswig-holstein.pmtiles and
    `tmp_path/tiles` as the dev server's tile directory."""
    lock = tmp_path / "tiles.lock"
    lock.write_text(LOCK, encoding="utf-8")
    (tmp_path / "tiles").mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", "-c", f'source "{DEVLINK_SH}" && link_dev_archive "$@"', "bash"]
        + [str(lock), str(tmp_path / "tiles"), archive],
        capture_output=True,
        encoding="utf-8",
    )


def test_an_archive_of_the_pinned_name_is_linked_for_the_dev_server(tmp_path: Path) -> None:
    result = link_dev_archive(tmp_path, "../../data/schleswig-holstein.pmtiles")

    assert result.returncode == 0, result.stderr
    link = tmp_path / "tiles" / "schleswig-holstein.pmtiles"
    assert link.readlink() == Path("../../data/schleswig-holstein.pmtiles")


def test_an_earlier_link_is_replaced(tmp_path: Path) -> None:
    (tmp_path / "tiles").mkdir()
    (tmp_path / "tiles" / "schleswig-holstein.pmtiles").symlink_to("../.cache/tiles/0.pmtiles")

    link_dev_archive(tmp_path, "../../data/schleswig-holstein.pmtiles")

    link = tmp_path / "tiles" / "schleswig-holstein.pmtiles"
    assert link.readlink() == Path("../../data/schleswig-holstein.pmtiles")


def test_an_archive_of_another_name_is_not_linked_and_says_why(tmp_path: Path) -> None:
    result = link_dev_archive(tmp_path, "../../data/denmark.pmtiles")

    assert result.returncode == 0, result.stderr
    assert list((tmp_path / "tiles").iterdir()) == []
    assert "serves only schleswig-holstein.pmtiles" in result.stdout
