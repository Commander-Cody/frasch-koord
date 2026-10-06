"""registry.py: the one reader of the dialect registry, names/dialects.csv."""

from __future__ import annotations

from pathlib import Path

import pytest

from frasch import registry
from frasch.__main__ import main
from frasch.errors import PipelineError, Problem, ValidationError

HEADER = "tag,column,label,status,view,note\n"
MOORING = "frr-x-mooring,mooring,Mooring,living,yes,\n"
FERING = "frr-x-fering,fering,Fering,living,no,\n"


def write(tmp_path: Path, text: str) -> str:
    path = tmp_path / "dialects.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_the_dialects_in_file_order(tmp_path: Path) -> None:
    reg = registry.read(write(tmp_path, HEADER + MOORING + FERING))
    assert reg.tags == ["frr-x-mooring", "frr-x-fering"]
    assert reg.columns == ["mooring", "fering"]
    assert reg.column_of("frr-x-fering") == "fering"


def test_every_broken_row_is_reported_at_once(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        HEADER
        + MOORING
        + "frr-x-fering,fering,Fering,alive,no,\n"  # line 3
        + "frr-x-solring,solring,,living,no,\n",
    )  # line 4
    with pytest.raises(ValidationError) as exc:
        registry.read(path)
    assert exc.value.problems == [
        Problem(path, 3, "status 'alive' (living / extinct)"),
        Problem(path, 4, "no label"),
    ]


def test_the_problems_are_in_the_order_of_the_lines(tmp_path: Path) -> None:
    # Whatever kind they are of: a broken rule above a comma too few.
    path = write(
        tmp_path,
        HEADER + "frr-x-fering,fering,Fering,alive,no,\n" + "frr-x-mooring,mooring,Mooring\n",
    )
    _, problems = registry.rows(path)
    assert [p.line for p in problems] == [2, 3]


def test_an_unknown_tag_is_a_pipeline_error(tmp_path: Path) -> None:
    reg = registry.read(write(tmp_path, HEADER + MOORING))
    with pytest.raises(PipelineError, match="frr-x-fering"):
        reg.column_of("frr-x-fering")


def test_the_frontend_gets_the_registry_without_the_notes(tmp_path: Path) -> None:
    reg = registry.read(
        write(tmp_path, HEADER + "frr-x-mooring,mooring,Mooring,living,yes,Bökingharde\n")
    )
    out = tmp_path / "generated" / "dialects.json"
    registry.export_json(reg, str(out))
    assert out.read_text(encoding="utf-8") == (
        '[{"tag":"frr-x-mooring","column":"mooring","label":"Mooring",'
        '"status":"living","view":"yes"}]\n'
    )


def test_the_export_command_writes_the_file_its_option_names(tmp_path: Path) -> None:
    out = tmp_path / "dialects.json"
    dialects_csv = write(tmp_path, HEADER + MOORING)
    assert main(["build", "dialects", "--dialects", dialects_csv, "--registry-json", str(out)]) == 0
    assert out.exists()
