"""frasch.cli, what every command shares: the path options, which name the
same file in every command, and a `main` that turns a broken input into its
message and exit status 1."""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

import pytest

from frasch import cli, registry
from frasch.errors import ValidationError
from frasch.paths import Workspace

REGISTRY_HEADER = "tag,column,label,status,view,note\n"


def parsed(options: list[str], argv: list[str]) -> Workspace:
    """The workspace of a command that takes the path `options`, run with `argv`."""
    ap = argparse.ArgumentParser()
    cli.add_workspace_options(ap, *options)
    return cli.workspace(ap.parse_args(argv))


def test_without_path_options_a_command_works_on_the_default_workspace() -> None:
    assert parsed(["names", "area_list"], []) == Workspace.default()


def test_a_path_option_replaces_its_file_alone() -> None:
    workspace = parsed(["names", "area_list"], ["--area-list", "other.csv"])
    assert workspace == dataclasses.replace(Workspace.default(), area_list="other.csv")


def test_a_path_option_the_command_does_not_take_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parsed(["names"], ["--area-list", "other.csv"])
    assert "unrecognized arguments: --area-list" in capsys.readouterr().err


def test_the_work_option_moves_every_scratch_file() -> None:
    assert parsed(["work"], ["--work", "scratch"]) == Workspace.default().with_work("scratch")


def test_a_scratch_file_named_by_its_own_option_stays_out_of_the_work_directory() -> None:
    workspace = parsed(["work", "candidates"], ["--candidates", "c.jsonl", "--work", "scratch"])
    assert workspace.candidates == "c.jsonl"


def test_a_broken_input_stops_the_library_with_a_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "dialects.csv"
    path.write_text(
        REGISTRY_HEADER + "frr-y-mooring,mooring,Mooring,living,yes,\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="dialects.csv:2: bad tag"):
        registry.read(str(path))


def test_the_command_reports_it_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "dialects.csv"
    path.write_text(
        REGISTRY_HEADER + "frr-y-mooring,mooring,Mooring,living,yes,\n", encoding="utf-8"
    )
    assert registry.main(["--dialects", str(path)]) == 1
    assert "dialects.csv:2: bad tag" in capsys.readouterr().err
