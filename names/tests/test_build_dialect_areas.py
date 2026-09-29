"""build_dialect_areas.py: dialect_areas.csv plus an extract become the
dialect areas, or the build stops and writes nothing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import build_dialect_areas as bda, paths, registry
from frasch.errors import ValidationError
from frasch import dialects
from frasch import provenance
from osm_fixture import ring, write_extract


# ------------------------------------------------------------- read_areas ---
def test_an_osm_reference_on_two_rows_is_refused(tmp_path: Path) -> None:
    # the review overlay's `?areas&area=` links name a row by its reference (#23)
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\n"
                     "frr-x-solring,relation/1147134,Sylt,\n"
                     "frr-x-solring,relation/1147133,Kampen,\n"
                     "frr-x-solring,relation/1147134,Sylt again,\n", encoding="utf-8")
    with pytest.raises(ValidationError, match=r"dialect_areas.csv:4: relation/1147134 "
                                         r"is already on line 2"):
        bda.read_areas(str(areas), registry.read())


# ------------------------------------------------------------------ main ---
# A tiny triangle way stands in for a whole municipality; `--registry` still
# points at the real dialects.csv so `frr-x-mooring` is a known tag.
def _write_fixture(tmp_path: Path, csv_rows: str,
                   timestamp: str | None = None) -> tuple[Path, Path]:
    nodes, way = ring(1, (8.80, 54.55), (8.82, 54.55), (8.82, 54.57))
    pbf = write_extract(tmp_path / "extract.osm.pbf", nodes=nodes,
                        ways={1: (way, {})}, timestamp=timestamp)
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\n" + csv_rows, encoding="utf-8")
    return pbf, areas


def test_main_exits_nonzero_on_a_missing_reference_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n"
                                          "frr-x-mooring,way/999,Missing,\n")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"
    out.write_bytes(b"stale-out")
    parts_out.write_bytes(b"stale-parts")

    assert bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                     "--parts-out", str(parts_out), "--no-unassigned"]) == 1

    message = capsys.readouterr().err
    assert "way/999" in message
    assert "Missing" in message
    assert "frr-x-mooring" in message
    # nothing was written -- neither file changed
    assert out.read_bytes() == b"stale-out"
    assert parts_out.read_bytes() == b"stale-parts"


def test_allow_missing_writes_despite_a_missing_reference(tmp_path: Path) -> None:
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n"
                                          "frr-x-mooring,way/999,Missing,\n")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                  "--parts-out", str(parts_out), "--no-unassigned",
                  "--allow-missing"])

    assert rc == 0
    assert out.exists()
    assert parts_out.exists()


def test_output_is_stamped_with_its_inputs(tmp_path: Path) -> None:
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/1,Existing,\n",
                                timestamp="2026-09-22T20:22:59Z")
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main([str(pbf), "--areas", str(areas), "--out", str(out),
                  "--parts-out", str(parts_out), "--no-unassigned"])

    assert rc == 0
    expected = {
        "dialect_areas.csv": provenance.blob_hash(areas),
        "dialects.csv": provenance.blob_hash(paths.DIALECTS),
        "extracts": [{"file": "extract.osm.pbf",
                      "replication_timestamp": "2026-09-22T20:22:59Z"}],
    }
    fc = json.loads(out.read_text())
    assert fc["properties"]["built_from"] == expected
    parts_fc = json.loads(parts_out.read_text())
    assert parts_fc["properties"]["built_from"] == expected
    # AreaIndex.from_geojson must keep working with the stamped file
    idx = dialects.AreaIndex.from_geojson(str(out))
    assert len(idx) == 1

