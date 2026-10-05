"""tiles/workspace.sh: build.sh names a file of the name pipeline to the
frasch commands only when its environment variable does -- otherwise a
command works on its own default, and the two cannot disagree."""

from __future__ import annotations

import subprocess
from pathlib import Path

WORKSPACE_SH = Path(__file__).resolve().parent.parent / "workspace.sh"


def workspace_options(env: dict[str, str], *files: str) -> list[str]:
    """The arguments `workspace_options <files>` gives a command, in an
    environment of `env` alone."""
    script = (
        f'source "{WORKSPACE_SH}" && workspace_options "$@" && '
        'for option in "${WORKSPACE_OPTIONS[@]}"; do printf "%s\\n" "$option"; done'
    )
    result = subprocess.run(
        ["bash", "-c", script, "bash", *files], capture_output=True, text=True, env=env, check=True
    )
    return result.stdout.splitlines()


def test_a_file_whose_variable_is_not_set_is_not_named() -> None:
    assert workspace_options({}, "names", "dialects") == []


def test_a_file_whose_variable_is_set_is_named_by_its_option() -> None:
    assert workspace_options({"AREAS": "my/areas.geojson"}, "names", "areas") == [
        "--areas",
        "my/areas.geojson",
    ]


def test_an_empty_variable_counts_as_not_set() -> None:
    assert workspace_options({"NAMES": ""}, "names") == []


def test_a_path_with_a_space_stays_one_argument() -> None:
    assert workspace_options({"NAMES": "my names/places.csv"}, "names") == [
        "--names",
        "my names/places.csv",
    ]


def test_only_the_files_asked_for_are_named() -> None:
    env = {"NAMES": "places.csv", "DIALECTS": "dialects.csv"}
    assert workspace_options(env, "dialects") == ["--dialects", "dialects.csv"]
