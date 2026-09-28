"""tiles/java.sh: which Java build.sh runs Planetiler with (#24 review).

A GA release prints its version without a dot (`"17"`), an update release
with one (`"21.0.2"`); both must be read, or an unsupported JDK slips past
the version check."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

JAVA_SH = Path(__file__).resolve().parent.parent / "java.sh"


def java_major(version_line: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", f'source "{JAVA_SH}" && java_major "$1"',
                           "bash", version_line], capture_output=True, text=True)


@pytest.mark.parametrize("line, major", [
    ('openjdk version "17" 2021-09-14', "17"),
    ('openjdk version "21" 2023-09-19', "21"),
    ('openjdk version "21.0.2" 2024-01-16', "21"),
    ('java version "1.8.0_392"', "1"),
])
def test_the_major_version_is_read_from_both_forms(line, major):
    result = java_major(line)
    assert (result.returncode, result.stdout.strip()) == (0, major)


def test_an_unreadable_version_line_fails():
    result = java_major("Error: could not find libjava.so")
    assert result.returncode != 0 and result.stdout == ""
