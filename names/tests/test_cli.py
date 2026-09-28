"""A command and the library under it: the library raises, the command's
`main` turns a broken input into its message and exit status 1."""
from __future__ import annotations

import pytest

from frasch import dialects, registry
from frasch.errors import ValidationError

REGISTRY_HEADER = "tag,column,label,status,view,note\n"


def test_a_broken_input_stops_the_library_with_a_validation_error(tmp_path):
    path = tmp_path / "dialects.csv"
    path.write_text(REGISTRY_HEADER + "frr-y-mooring,mooring,Mooring,living,yes,\n",
                    encoding="utf-8")
    with pytest.raises(ValidationError, match="dialects.csv:2: bad tag"):
        registry.read(str(path))


def test_the_command_reports_it_and_exits_1(tmp_path, capsys):
    path = tmp_path / "dialects.csv"
    path.write_text(REGISTRY_HEADER + "frr-y-mooring,mooring,Mooring,living,yes,\n",
                    encoding="utf-8")
    assert dialects.main(["--registry", str(path)]) == 1
    assert "dialects.csv:2: bad tag" in capsys.readouterr().err
