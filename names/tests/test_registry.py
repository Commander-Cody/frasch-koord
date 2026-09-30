"""registry.py: the one reader of the dialect registry, names/dialects.csv."""
from __future__ import annotations

from pathlib import Path

import pytest

from frasch import registry
from frasch.errors import ValidationError

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
    path = write(tmp_path, HEADER + MOORING
                 + "frr-x-fering,fering,Fering,alive,no,\n"      # line 3
                 + "frr-x-solring,solring,,living,no,\n")        # line 4
    with pytest.raises(ValidationError) as exc:
        registry.read(path)
    assert exc.value.problems == [f"{path}:3: status 'alive' (living / extinct)",
                                  f"{path}:4: no label"]


def test_an_unknown_tag_is_a_validation_error(tmp_path: Path) -> None:
    reg = registry.read(write(tmp_path, HEADER + MOORING))
    with pytest.raises(ValidationError, match="frr-x-fering"):
        reg.column_of("frr-x-fering")
