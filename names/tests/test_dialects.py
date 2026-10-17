"""dialects.py: the one reader of the dialect registry, names/dialects.csv."""

from __future__ import annotations

from pathlib import Path

import pytest

from frasch import dialects
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
    reg = dialects.read(write(tmp_path, HEADER + MOORING + FERING))
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
        dialects.read(path)
    assert exc.value.problems == [
        Problem(path, 3, "status 'alive' (living / extinct)"),
        Problem(path, 4, "no label"),
    ]


BAD_TAG = "-- expected frr-x-<subtag>, subtags [a-z0-9] and at most 8 characters each"


@pytest.mark.parametrize(
    "row, problem",
    [
        ("frr-x-mooringen,mooringen,Mooring,living,yes,", f"bad tag 'frr-x-mooringen' {BAD_TAG}"),
        ("mooring,mooring,Mooring,living,yes,", f"bad tag 'mooring' {BAD_TAG}"),
        ("frr-x-mooring,Mooring,Mooring,living,yes,", "bad column name 'Mooring'"),
        (
            "frr-x-local,local,Local,living,yes,",
            "'local' is a reserved column of places.csv, not a dialect",
        ),
        ("frr-x-mooring,mooring,Mooring,alive,yes,", "status 'alive' (living / extinct)"),
        ("frr-x-mooring,mooring,Mooring,living,maybe,", "view 'maybe' (yes / no)"),
        ("frr-x-mooring,mooring,,living,yes,", "no label"),
    ],
    ids=[
        "subtag too long",
        "not frr-x",
        "column not lowercase",
        "local",
        "status",
        "view",
        "label",
    ],
)
def test_a_row_that_breaks_a_rule_is_reported_with_it(
    tmp_path: Path, row: str, problem: str
) -> None:
    path = write(tmp_path, HEADER + row + "\n")
    assert dialects.rows(path)[1] == [Problem(path, 2, problem)]


@pytest.mark.parametrize(
    "second",
    ["frr-x-mooring,mooring,Mooring,living,yes,", "frr-x-moring,mooring,Moring,living,no,"],
    ids=["the same row", "a new tag for the same column"],
)
def test_a_column_registered_twice_is_reported_on_the_second_row(
    tmp_path: Path, second: str
) -> None:
    path = write(tmp_path, HEADER + MOORING + second + "\n")
    assert [p.line for p in dialects.rows(path)[1]] == [3]


def test_the_problems_are_in_the_order_of_the_lines(tmp_path: Path) -> None:
    # Whatever kind they are of: a broken rule above a comma too few.
    path = write(
        tmp_path,
        HEADER + "frr-x-fering,fering,Fering,alive,no,\n" + "frr-x-mooring,mooring,Mooring\n",
    )
    _, problems = dialects.rows(path)
    assert [p.line for p in problems] == [2, 3]


def test_an_unknown_tag_is_a_pipeline_error(tmp_path: Path) -> None:
    reg = dialects.read(write(tmp_path, HEADER + MOORING))
    with pytest.raises(PipelineError, match="frr-x-fering"):
        reg.column_of("frr-x-fering")


def test_the_frontend_gets_the_registry_without_notes_and_columns(tmp_path: Path) -> None:
    reg = dialects.read(
        write(tmp_path, HEADER + "frr-x-mooring,mooring,Mooring,living,yes,Bökingharde\n")
    )
    out = tmp_path / "generated" / "dialects.json"
    dialects.export_json(reg, str(out))
    assert out.read_text(encoding="utf-8") == (
        '[{"tag":"frr-x-mooring","label":"Mooring","status":"living","view":"yes"}]\n'
    )


def test_the_export_command_writes_the_file_its_option_names(tmp_path: Path) -> None:
    out = tmp_path / "dialects.json"
    dialects_csv = write(tmp_path, HEADER + MOORING)
    assert main(["build", "dialects", "--dialects", dialects_csv, "--registry-json", str(out)]) == 0
    assert out.exists()
