"""build_dialect_areas.py: dialect_areas.csv plus an extract become the
dialect areas, or the build stops and writes nothing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from frasch import build_dialect_areas as bda, paths, registry
from frasch.errors import ValidationError
from frasch import dialects
from frasch import provenance
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
        bda.read_areas(str(areas), registry.read())


# ------------------------------------------------------------------ main ---
# A tiny triangle way stands in for a whole municipality; `--registry` still
# points at the real dialects.csv so `frr-x-mooring` is a known tag.
def _write_fixture(
    tmp_path: Path, csv_rows: str, timestamp: str | None = None
) -> tuple[Path, Path]:
    nodes, way = ring(1, (8.80, 54.55), (8.82, 54.55), (8.82, 54.57))
    pbf = write_extract(
        tmp_path / "extract.osm.pbf", nodes=nodes, ways={1: (way, {})}, timestamp=timestamp
    )
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text("dialect,osm,name,note\n" + csv_rows, encoding="utf-8")
    return pbf, areas


def test_main_exits_nonzero_on_a_missing_reference_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pbf, areas = _write_fixture(
        tmp_path, "frr-x-mooring,way/1,Existing,\nfrr-x-mooring,way/999,Missing,\n"
    )
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"
    out.write_bytes(b"stale-out")
    parts_out.write_bytes(b"stale-parts")

    assert (
        bda.main(
            [
                str(pbf),
                "--areas",
                str(areas),
                "--out",
                str(out),
                "--parts-out",
                str(parts_out),
                "--no-unassigned",
            ]
        )
        == 1
    )

    message = capsys.readouterr().err
    assert "way/999" in message
    assert "Missing" in message
    assert "frr-x-mooring" in message
    # nothing was written -- neither file changed
    assert out.read_bytes() == b"stale-out"
    assert parts_out.read_bytes() == b"stale-parts"


def test_allow_missing_writes_despite_a_missing_reference(tmp_path: Path) -> None:
    pbf, areas = _write_fixture(
        tmp_path, "frr-x-mooring,way/1,Existing,\nfrr-x-mooring,way/999,Missing,\n"
    )
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main(
        [
            str(pbf),
            "--areas",
            str(areas),
            "--out",
            str(out),
            "--parts-out",
            str(parts_out),
            "--no-unassigned",
            "--allow-missing",
        ]
    )

    assert rc == 0
    assert out.exists()
    assert parts_out.exists()


def test_output_is_stamped_with_its_inputs(tmp_path: Path) -> None:
    pbf, areas = _write_fixture(
        tmp_path, "frr-x-mooring,way/1,Existing,\n", timestamp="2026-09-22T20:22:59Z"
    )
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"

    rc = bda.main(
        [
            str(pbf),
            "--areas",
            str(areas),
            "--out",
            str(out),
            "--parts-out",
            str(parts_out),
            "--no-unassigned",
        ]
    )

    assert rc == 0
    expected = {
        "dialect_areas.csv": provenance.blob_hash(areas),
        "dialects.csv": provenance.blob_hash(paths.DIALECTS),
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


def _write_district(tmp_path: Path) -> tuple[Path, Path, Path]:
    """-> (first extract, second extract, dialect_areas.csv)."""
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
    areas = tmp_path / "dialect_areas.csv"
    areas.write_text(
        "dialect,osm,name,note\n"
        "frr-x-mooring,way/1,Existing,a way\n"
        "frr-x-solring,relation/100,Claimedtown,a municipality\n"
        "frr-x-solring,way/8,Second,only in the second extract\n",
        encoding="utf-8",
    )
    return first, second, areas


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """-> (exit status, stdout, stderr), the scan times blanked."""
    rc = bda.main(argv)
    out, err = capsys.readouterr()
    return rc, re.sub(r"\(\d+s\)", "(Ns)", out), err


def test_main_reports_every_step_of_a_full_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second, areas = _write_district(tmp_path)
    out = tmp_path / "areas.geojson"
    parts_out = tmp_path / "parts.geojson"
    argv = [str(first), str(second), "--areas", str(areas), "--out", str(out)]

    rc, stdout, stderr = _run([*argv, "--parts-out", str(parts_out)], capsys)

    assert rc == 0
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


def test_main_without_parts_out_skips_the_unassigned_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second, areas = _write_district(tmp_path)
    out = tmp_path / "areas.geojson"
    argv = [str(first), "--areas", str(areas), "--out", str(out), "--allow-missing"]

    rc, stdout, stderr = _run([*argv, "--parts-out", ""], capsys)

    assert rc == 0
    assert stderr == ""
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


def test_main_refuses_with_the_report_of_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second, areas = _write_district(tmp_path)
    out = tmp_path / "areas.geojson"

    rc, stdout, stderr = _run([str(first), "--areas", str(areas), "--out", str(out)], capsys)

    assert rc == 1
    assert stdout.endswith(
        "  ! relation/100: 1 unclosed outer ring(s) -- skipped\n"
        "\n"
        "1 object(s) not found in the extract(s):\n"
        "  way/8  Second (frr-x-solring)\n"
    )
    assert stderr == (
        "1 object(s) not found in the extract(s):\n"
        "  way/8  Second (frr-x-solring)\n"
        "\n"
        "run with --allow-missing to build anyway; nothing was written\n"
    )
    assert not out.exists()


def test_main_refuses_when_no_reference_produced_any_geometry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pbf, areas = _write_fixture(tmp_path, "frr-x-mooring,way/999,Missing,\n")
    out = tmp_path / "areas.geojson"

    rc, _stdout, stderr = _run(
        [str(pbf), "--areas", str(areas), "--out", str(out), "--allow-missing"], capsys
    )

    assert rc == 1
    assert stderr == "no geometry found -- is the extract the right region?\n"
    assert not out.exists()
