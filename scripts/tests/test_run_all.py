"""scripts/run-all.sh: runs every command it is given, keeps going after a
failure, and names the failed ones at the end (`just check`, `npm run check`).

Runs the script itself through bash, with commands that leave a trace in a
temp directory, so the tests see what really ran."""

from __future__ import annotations

import subprocess
from pathlib import Path

RUN_ALL = Path(__file__).resolve().parent.parent / "run-all.sh"


def run_all(cwd: Path, *commands: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUN_ALL), *commands], cwd=cwd, capture_output=True, text=True
    )


def test_runs_every_command_and_passes_when_all_pass(tmp_path: Path) -> None:
    result = run_all(tmp_path, "echo lint >> ran", "echo test >> ran")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "ran").read_text() == "lint\ntest\n"


def test_keeps_going_after_a_failure_and_fails_at_the_end(tmp_path: Path) -> None:
    result = run_all(tmp_path, "echo lint >> ran; exit 3", "echo test >> ran")

    assert result.returncode == 1
    assert (tmp_path / "ran").read_text() == "lint\ntest\n"
    assert result.stderr.splitlines()[-1] == "run-all: failed: echo lint >> ran; exit 3"


def test_names_every_failed_command_in_order(tmp_path: Path) -> None:
    result = run_all(tmp_path, "exit 1", "true", "exit 2")

    assert result.returncode == 1
    assert result.stderr.splitlines() == ["run-all: failed: exit 1", "run-all: failed: exit 2"]


def test_announces_each_command_before_its_output(tmp_path: Path) -> None:
    result = run_all(tmp_path, "echo linting", "echo testing")

    assert result.stdout.splitlines() == [
        "run-all: echo linting",
        "linting",
        "run-all: echo testing",
        "testing",
    ]
