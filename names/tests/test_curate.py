"""The command line of `frasch curate`.  (Its export is covered in
test_worklist.py, `apply` in test_curate_apply.py, reading the patch in
test_patch.py.)"""

from __future__ import annotations

from pathlib import Path

import pytest

from frasch.__main__ import main
from conftest import path_options, places_text, workspace


@pytest.mark.parametrize(
    "argv,hint",
    [
        (["--dry-run"], "frasch curate apply --dry-run"),
        (["--names", "places.csv", "--keep"], "frasch curate apply --names places.csv --keep"),
    ],
)
def test_an_apply_option_without_a_subcommand_points_at_apply(
    argv: list[str], hint: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["curate", *argv])
    assert exc.value.code == 2
    assert f"did you mean `{hint}`?" in capsys.readouterr().err


def test_options_without_a_subcommand_mean_export(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (world / "places.csv").write_text(places_text([]), encoding="utf-8")
    files = path_options(workspace(world), "names", "dialects", "work")
    assert main(["curate", *files]) == 1
    assert "run `frasch match` first" in capsys.readouterr().err
