"""`frasch <command>`: the one entry point of the pipeline and its command
table (frasch/__main__.py)."""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from frasch.__main__ import main

COMMANDS = [
    "check-inputs",
    "candidates",
    "match",
    "objects",
    "areas",
    "dialects",
    "index",
    "provenance",
    "update",
    "check-outputs",
    "curate",
    "inject",
    "check-tiles",
]


@pytest.fixture
def dialects_csv(tmp_path: Path) -> str:
    path = tmp_path / "dialects.csv"
    path.write_text(
        "tag,column,label,status,view,note\n"
        "frr-x-mooring,mooring,Mooring,living,yes,\n"
        "frr-x-fering,fering,Fering,living,no,\n",
        encoding="utf-8",
    )
    return str(path)


def test_a_command_runs_with_the_arguments_after_its_name(
    dialects_csv: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["dialects", "--tags", "--dialects", dialects_csv]) == 0
    assert capsys.readouterr().out == "frr-x-mooring,frr-x-fering\n"


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_of_the_table_explains_itself(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        main([command, "--help"])
    assert stop.value.code == 0
    assert f"usage: frasch {command}" in capsys.readouterr().out


def test_the_help_lists_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    listed = [
        line.split()[0] for line in capsys.readouterr().out.split("commands:\n")[1].splitlines()
    ]
    assert listed == COMMANDS


def test_an_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["locate"])
    assert stop.value.code == 2
    assert "invalid choice: 'locate'" in capsys.readouterr().err


def test_the_package_runs_as_a_module(dialects_csv: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "frasch", "dialects", "--tags", "--dialects", dialects_csv],
        capture_output=True,
        text=True,
    )
    assert (result.returncode, result.stdout) == (0, "frr-x-mooring,frr-x-fering\n")


def test_the_frasch_script_is_installed_for_the_command_table() -> None:
    [script] = entry_points(group="console_scripts", name="frasch")
    assert script.value == "frasch.__main__:main"
