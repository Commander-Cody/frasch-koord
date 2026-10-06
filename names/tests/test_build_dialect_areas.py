"""`frasch areas`: dialect_areas.csv plus an extract become the
dialect areas, or the build stops and writes nothing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from frasch import build_dialect_areas as bda
from frasch.__main__ import main
from frasch.errors import PipelineError, ValidationError
from frasch import dialects
from frasch import provenance
from frasch.paths import Workspace
from conftest import REGISTRY, path_options
from osm_fixture import RingNodes, ring, write_extract


# ------------------------------------------------------------- read_areas ---
def test_an_osm_reference_on_two_rows_is_refused(tmp_path: Path) -> None:
    # the review overlay's `?areas&area=` links name a row by its reference (#23)
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\n"
        "frr-x-solring,relation/1147134,Sylt,\n"
        "frr-x-solring,relation/1147133,Kampen,\n"
        "frr-x-solring,relation/1147134,Sylt again,\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValidationError,
        match=r"dialect_areas.csv:4: relation/1147134 "
        r"is already on line 2",
    ):
        bda.read_areas(str(areas), REGISTRY)


# ------------------------------------------------------------------- run ---
# A tiny triangle way stands in for a whole municipality.
def _write_fixture(ws: Workspace, csv_rows: str, timestamp: str | None = None) -> Path:
    """Write the area list of `ws` and an extract next to it; -> the extract."""
    nodes, way = ring(1, (8.80, 54.55), (8.82, 54.55), (8.82, 54.57))
    areas = Path(ws.area_list)
    areas.write_text("dialect,osm,name,note\n" + csv_rows, encoding="utf-8")
    return write_extract(
        areas.parent / "extract.osm.pbf", nodes=nodes, ways={1: (way, {})}, timestamp=timestamp
    )


def test_a_missing_reference_stops_the_build_and_nothing_is_written(ws: Workspace) -> None:
    pbf = _write_fixture(ws, "frr-x-mooring,way/1,Existing,\nfrr-x-mooring,way/999,Missing,\n")
    out, parts_out = Path(ws.areas), Path(ws.parts)
    out.write_bytes(b"stale-out")
    parts_out.write_bytes(b"stale-parts")

    with pytest.raises(PipelineError) as stop:
        bda.run(ws, REGISTRY, [pbf], bda.Options(unassigned_ags=None))

    message = str(stop.value)
    assert "way/999" in message
    assert "Missing" in message
    assert "frr-x-mooring" in message
    # nothing was written -- neither file changed
    assert out.read_bytes() == b"stale-out"
    assert parts_out.read_bytes() == b"stale-parts"


def test_allow_missing_writes_despite_a_missing_reference(ws: Workspace) -> None:
    pbf = _write_fixture(ws, "frr-x-mooring,way/1,Existing,\nfrr-x-mooring,way/999,Missing,\n")

    bda.run(ws, REGISTRY, [pbf], bda.Options(unassigned_ags=None, allow_missing=True))

    assert Path(ws.areas).exists()
    assert Path(ws.parts).exists()


def test_output_is_stamped_with_its_inputs(ws: Workspace) -> None:
    pbf = _write_fixture(ws, "frr-x-mooring,way/1,Existing,\n", timestamp="2026-09-22T20:22:59Z")
    out, parts_out = Path(ws.areas), Path(ws.parts)

    bda.run(ws, REGISTRY, [pbf], bda.Options(unassigned_ags=None))

    expected = {
        "dialect_areas.csv": provenance.blob_hash(ws.area_list),
        "dialects.csv": provenance.blob_hash(ws.dialects),
        "extracts": [{"file": "extract.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}],
    }
    fc = json.loads(out.read_text())
    assert fc["properties"]["built_from"] == expected
    parts_fc = json.loads(parts_out.read_text())
    assert parts_fc["properties"]["built_from"] == expected
    # AreaIndex.from_geojson must keep working with the stamped file
    idx = dialects.AreaIndex.from_geojson(str(out))
    assert len(idx) == 1


# A Kreis Nordfriesland in miniature: two municipality relations the CSV
# claims or not, plus the relations the unassigned scan must pass over.
def _admin(key: str, name: str, **extra: str) -> dict[str, str]:
    """A municipality relation's tags; `extra` overrides any of them."""
    tags = {"boundary": "administrative", "admin_level": "8", "de:regionalschluessel": key}
    return tags | {"name": name} | extra


def _square(first_id: int, lon: float) -> tuple[RingNodes, list[int]]:
    """A 0.02-degree square ring with its south-west corner at `lon`."""
    return ring(first_id, (lon, 54.60), (lon + 0.02, 54.60), (lon + 0.02, 54.62), (lon, 54.62))


def _write_district(ws: Workspace) -> tuple[Path, Path]:
    """Write the area list of `ws` and two extracts next to it; -> the extracts."""
    tmp_path = Path(ws.area_list).parent
    nodes, way1 = ring(1, (8.80, 54.55), (8.82, 54.55), (8.82, 54.57))
    squares = {w: _square(w, lon) for w, lon in ((10, 8.90), (20, 8.93), (30, 8.96), (40, 9.50))}
    for square_nodes, _ in squares.values():
        nodes |= square_nodes
    nodes |= {14: ((8.99, 54.70), {}), 15: ((8.995, 54.71), {})}
    ways: dict[int, tuple[list[int], dict[str, str]]] = {
        1: (way1, {}),
        11: ([14, 15], {}),
        70: ([14, 15], {}),
    }
    ways |= {w: (refs, {}) for w, (_, refs) in squares.items()}
    relations = {
        100: ([("w", 10, "outer"), ("w", 11, "outer")], _admin("010540001000", "Claimedtown")),
        200: ([("w", 20, "outer")], _admin("010540002000", "Freetown")),
        300: (
            [("w", 30, "outer")],
            {
                "boundary": "administrative",
                "admin_level": "8",
                "de:amtlicher_gemeindeschluessel": "01054003",
            },
        ),
        400: ([("w", 40, "outer")], _admin("010560001000", "Pinneberg town")),
        500: ([("w", 40, "outer")], _admin("010540000000", "Amt", admin_level="7")),
        600: ([("w", 40, "outer")], _admin("010540006000", "Park", boundary="protected_area")),
        700: ([("w", 70, "outer")], _admin("010540007000", "Brokentown")),
    }
    first = write_extract(tmp_path / "first.osm.pbf", nodes=nodes, ways=ways, relations=relations)
    second_nodes, way8 = ring(80, (8.70, 54.50), (8.72, 54.50), (8.72, 54.52))
    second_nodes |= squares[20][0]
    second = write_extract(
        tmp_path / "second.osm.pbf",
        nodes=second_nodes,
        ways={8: (way8, {}), 20: (squares[20][1], {})},
        relations={200: relations[200]},
    )
    Path(ws.area_list).write_text(
        "dialect,osm,name,note\n"
        "frr-x-mooring,way/1,Existing,a way\n"
        "frr-x-solring,relation/100,Claimedtown,a municipality\n"
        "frr-x-solring,way/8,Second,only in the second extract\n",
        encoding="utf-8",
    )
    return first, second


def _printed(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    """-> (stdout, stderr), the scan times blanked."""
    out, err = capsys.readouterr()
    return re.sub(r"\(\d+s\)", "(Ns)", out), err


def test_a_full_build_reports_every_step(ws: Workspace, capsys: pytest.CaptureFixture[str]) -> None:
    first, second = _write_district(ws)
    areas, out, parts_out = ws.area_list, Path(ws.areas), Path(ws.parts)

    bda.run(ws, REGISTRY, [first, second])

    stdout, stderr = _printed(capsys)
    assert stderr == ""
    # the second extract is only asked for what the first one lacked, and
    # Freetown, already found there, is not counted again; Brokentown's
    # broken ring is not reported, nobody claims it
    assert stdout == (
        f"area list : {areas} -> 3 OSM objects, 2 dialects\n"
        "first.osm.pbf: 1/1 relations, 6 ways, 17 nodes, 3 unclaimed municipalities (Ns)\n"
        "second.osm.pbf: 0/0 relations, 1 ways, 3 nodes (Ns)\n"
        "  frr-x-mooring    1 object(s) ->  1 polygon(s),      1.4 km², valid=True, ~9 coords\n"
        "  frr-x-solring    2 object(s) ->  2 polygon(s),      4.3 km², valid=True, ~19 coords\n"
        "  ! relation/100: 1 unclosed outer ring(s) -- skipped\n"
        "\n"
        f"wrote {out} (2 features, 3 polygons, 1 kB)\n"
        "reads back as 3 polygon(s): frr-x-mooring (1), frr-x-solring (2)\n"
        f"wrote {parts_out} (5 features: 3 assigned, 2 unassigned, 2 kB)\n"
    )
    fc = json.loads(out.read_text())
    assert [f["properties"] for f in fc["features"]] == [
        {"dialect": "frr-x-mooring", "label": "Mooring"},
        {"dialect": "frr-x-solring", "label": "Sölring"},
    ]
    assert fc["features"][1]["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [
            [[[8.72, 54.52], [8.72, 54.5], [8.7, 54.5], [8.72, 54.52]]],
            [[[8.9, 54.62], [8.92, 54.62], [8.92, 54.6], [8.9, 54.6], [8.9, 54.62]]],
        ],
    }
    parts_fc = json.loads(parts_out.read_text())
    assert parts_fc["properties"]["unassigned_ags"] == "01054"
    assert [f["properties"] for f in parts_fc["features"]] == [
        {
            "fid": 1,
            "assigned": True,
            "dialect": "frr-x-mooring",
            "label": "Mooring",
            "name": "Existing",
            "note": "a way",
            "osm": "way/1",
            "line": 2,
            "km2": 1.4,
        },
        {
            "fid": 2,
            "assigned": True,
            "dialect": "frr-x-solring",
            "label": "Sölring",
            "name": "Claimedtown",
            "note": "a municipality",
            "osm": "relation/100",
            "line": 3,
            "km2": 2.9,
        },
        {
            "fid": 3,
            "assigned": True,
            "dialect": "frr-x-solring",
            "label": "Sölring",
            "name": "Second",
            "note": "only in the second extract",
            "osm": "way/8",
            "line": 4,
            "km2": 1.4,
        },
        {"fid": 4, "assigned": False, "name": "", "osm": "relation/300", "km2": 2.9},
        {"fid": 5, "assigned": False, "name": "Freetown", "osm": "relation/200", "km2": 2.9},
    ]


def test_a_build_without_the_parts_skips_the_unassigned_scan(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second = _write_district(ws)
    areas, out = ws.area_list, ws.areas

    bda.run(ws, REGISTRY, [first], bda.Options(allow_missing=True, parts=False))

    stdout, stderr = _printed(capsys)
    assert stderr == ""
    assert not Path(ws.parts).exists()
    assert stdout == (
        f"area list : {areas} -> 3 OSM objects, 2 dialects\n"
        "first.osm.pbf: 1/1 relations, 3 ways, 9 nodes (Ns)\n"
        "  frr-x-mooring    1 object(s) ->  1 polygon(s),      1.4 km², valid=True, ~9 coords\n"
        "  frr-x-solring    1 object(s) ->  1 polygon(s),      2.9 km², valid=True, ~11 coords\n"
        "  ! relation/100: 1 unclosed outer ring(s) -- skipped\n"
        "\n"
        "1 object(s) not found in the extract(s):\n"
        "  way/8  Second (frr-x-solring)\n"
        "\n"
        f"wrote {out} (2 features, 2 polygons, 1 kB)\n"
        "reads back as 2 polygon(s): frr-x-mooring (1), frr-x-solring (1)\n"
    )


def test_a_build_refuses_with_the_report_of_what_is_missing(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second = _write_district(ws)

    with pytest.raises(PipelineError) as stop:
        bda.run(ws, REGISTRY, [first])

    assert _printed(capsys)[0].endswith(
        "  ! relation/100: 1 unclosed outer ring(s) -- skipped\n"
        "\n"
        "1 object(s) not found in the extract(s):\n"
        "  way/8  Second (frr-x-solring)\n"
    )
    assert str(stop.value) == (
        "1 object(s) not found in the extract(s):\n"
        "  way/8  Second (frr-x-solring)\n"
        "\n"
        "run with --allow-missing to build anyway; nothing was written"
    )
    assert not Path(ws.areas).exists()


def test_a_build_refuses_when_no_reference_produced_any_geometry(ws: Workspace) -> None:
    pbf = _write_fixture(ws, "frr-x-mooring,way/999,Missing,\n")

    with pytest.raises(
        PipelineError, match=r"^no geometry found -- is the extract the right region\?$"
    ):
        bda.run(ws, REGISTRY, [pbf], bda.Options(allow_missing=True))

    assert not Path(ws.areas).exists()


def test_the_command_builds_the_files_its_options_name_and_fails_on_a_missing_reference(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second = _write_district(ws)
    files = path_options(ws, "area_list", "dialects", "areas", "parts")

    assert main(["areas", str(first), *files, "--no-parts"]) == 1

    assert capsys.readouterr().err.endswith(
        "run with --allow-missing to build anyway; nothing was written\n"
    )
