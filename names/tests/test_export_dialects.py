"""names/dialects.py: the dialect registry, exported for the frontend."""

from __future__ import annotations

from pathlib import Path

from frasch import export_dialects


def test_the_frontend_gets_the_registry_without_the_notes(tmp_path: Path) -> None:
    registry = tmp_path / "dialects.csv"
    registry.write_text(
        "tag,column,label,status,view,note\nfrr-x-mooring,mooring,Mooring,living,yes,Bökingharde\n",
        encoding="utf-8",
    )
    out = tmp_path / "generated" / "dialects.json"
    export_dialects.main(["--registry", str(registry), "--export", str(out)])
    assert out.read_text(encoding="utf-8") == (
        '[{"tag":"frr-x-mooring","column":"mooring","label":"Mooring",'
        '"status":"living","view":"yes"}]\n'
    )
