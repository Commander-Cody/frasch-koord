"""`frasch areas`: dialect_areas.csv plus an extract become the
dialect areas, or the build stops and writes nothing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from frasch import build_dialect_areas as bda
from frasch import refs
from frasch.dialect_areas import AreaRow
from frasch.__main__ import main
from frasch.errors import PipelineError, ValidationError
from frasch import dialect_areas
from frasch import provenance
from frasch.paths import Workspace
from conftest import REGISTRY, path_options, schema_problems
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


# ------------------------------------------------------------------ build ---
SOURCE = bda.Source("dialect_areas.csv", {"extracts": []})


def _row(line: int, dialect: str, osm: str, name: str = "", note: str = "") -> AreaRow:
    """A row of the area list as `read_areas` gives it."""
    named = refs.osm_only(refs.parse(osm))
    return {"line": line, "dialect": dialect, "name": name, "note": note, "osm": osm, "refs": named}


def _area(feature: bda.Feature[Any]) -> BaseGeometry:
    return shape(cast(dict[str, Any], feature["geometry"]))


def test_a_dialect_is_the_dissolved_polygons_of_its_rows() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-mooring", "way/2")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1), ("w", 2): box(8.1, 54.0, 8.2, 54.1)})

    areas = bda.build(rows, REGISTRY, found, SOURCE)

    (feature,) = areas.dialects["features"]
    assert _area(feature).equals(box(8.0, 54.0, 8.2, 54.1))


def test_a_build_says_nothing_itself(capsys: pytest.CaptureFixture[str]) -> None:
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-mooring", "way/999", "Missing")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)}, problems=["way/999: a problem"])

    bda.build(rows, REGISTRY, found, SOURCE)

    assert capsys.readouterr() == ("", "")


def test_the_report_of_a_build_lists_the_references_without_geometry() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-solring", "way/999", "Missing")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    areas = bda.build(rows, REGISTRY, found, SOURCE)

    assert areas.report[-3:] == [
        "",
        "1 object(s) not found in the extract(s):",
        "  way/999  Missing (frr-x-solring)",
    ]


def test_a_reference_written_twice_on_a_row_is_missing_once() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-mooring", "way/999; way/999")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    assert bda.build(rows, REGISTRY, found, SOURCE).missing == 1


def test_a_reference_written_twice_on_a_row_is_one_object_of_its_dialect() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1; way/1")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    (line,) = bda.build(rows, REGISTRY, found, SOURCE).report

    assert line.startswith("  frr-x-mooring    1 object(s) ->  1 polygon(s)")


def test_a_municipality_no_row_claims_is_a_part_without_a_dialect() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1", "Existing")]
    found = bda.Scan(
        {("w", 1): box(8.0, 54.0, 8.1, 54.1)},
        {("r", 200): bda.Municipality("Freetown", box(8.1, 54.0, 8.2, 54.1))},
    )

    parts = bda.build(rows, REGISTRY, found, SOURCE).parts

    assert parts is not None
    assert parts.fc["features"][1]["properties"] == {
        "assigned": False,
        "name": "Freetown",
        "osm": "relation/200",
        "km2": 72.8,  # 0.1 x 0.1 degrees at 54.05 N: 11.132 km x 6.535 km
    }


def test_the_report_of_a_build_has_a_line_per_dialect() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    assert bda.build(rows, REGISTRY, found, SOURCE).report == [
        "  frr-x-mooring    1 object(s) ->  1 polygon(s),     72.8 km², valid=True, ~11 coords"
    ]


def test_the_report_of_a_build_flags_each_ring_problem_of_the_scan() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)}, problems=["way/1: a problem"])

    assert bda.build(rows, REGISTRY, found, SOURCE).report[1:] == ["  ! way/1: a problem"]


def test_a_build_counts_the_polygons_of_every_dialect() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-solring", "way/2; way/3")]
    found = bda.Scan(
        {
            ("w", 1): box(8.0, 54.0, 8.1, 54.1),
            ("w", 2): box(8.2, 54.0, 8.3, 54.1),
            ("w", 3): box(8.4, 54.0, 8.5, 54.1),
        }
    )

    assert bda.build(rows, REGISTRY, found, SOURCE).polygons == 3


def test_the_feature_of_a_dialect_carries_its_tag_and_label() -> None:
    rows = [_row(2, "frr-x-solring", "way/1")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    (feature,) = bda.build(rows, REGISTRY, found, SOURCE).dialects["features"]

    assert feature["properties"] == {"dialect": "frr-x-solring", "label": "Sölring"}


def test_an_assigned_part_carries_its_rows_dialect_name_note_and_line() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1", "Existing", "a way")]
    found = bda.Scan({("w", 1): box(8.0, 54.0, 8.1, 54.1)})

    parts = bda.build(rows, REGISTRY, found, SOURCE).parts

    assert parts is not None
    assert parts.fc["features"][0]["properties"] == {
        "assigned": True,
        "dialect": "frr-x-mooring",
        "name": "Existing",
        "note": "a way",
        "osm": "way/1",
        "line": 2,
        "km2": 72.8,
    }


def _with_two_unclaimed() -> bda.Scan:
    """A scan of one claimed way and two unclaimed municipalities, the one
    with the lower id named last."""
    return bda.Scan(
        {("w", 1): box(8.0, 54.0, 8.1, 54.1)},
        {
            ("r", 100): bda.Municipality("Bdorf", box(8.1, 54.0, 8.2, 54.1)),
            ("r", 200): bda.Municipality("Adorf", box(8.2, 54.0, 8.3, 54.1)),
        },
    )


def test_the_unassigned_parts_follow_the_assigned_ones_by_name() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1", "Existing")]

    parts = bda.build(rows, REGISTRY, _with_two_unclaimed(), SOURCE).parts

    assert parts is not None
    assert [f["properties"]["name"] for f in parts.fc["features"]] == [
        "Existing",
        "Adorf",
        "Bdorf",
    ]


def test_a_build_counts_the_municipalities_no_row_claims() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1")]

    parts = bda.build(rows, REGISTRY, _with_two_unclaimed(), SOURCE).parts

    assert parts is not None
    assert parts.unassigned == 2


def test_the_parts_name_the_district_of_their_unassigned_municipalities() -> None:
    rows = [_row(2, "frr-x-mooring", "way/1")]

    parts = bda.build(rows, REGISTRY, _with_two_unclaimed(), SOURCE).parts

    assert parts is not None
    assert parts.fc["properties"]["unassigned_ags"] == "01054"


def test_a_build_without_the_parts_scans_for_no_unclaimed_municipalities() -> None:
    assert bda.Options(parts=False).scanned_ags is None


# ------------------------------------------------------------------ write ---
def _built() -> bda.Areas:
    """The areas of one dialect of two rows, apart, with one unclaimed
    municipality."""
    rows = [_row(2, "frr-x-mooring", "way/1"), _row(3, "frr-x-mooring", "way/2")]
    found = bda.Scan(
        {("w", 1): box(8.0, 54.0, 8.1, 54.1), ("w", 2): box(8.2, 54.0, 8.3, 54.1)},
        {("r", 200): bda.Municipality("Freetown", box(8.1, 54.0, 8.2, 54.1))},
    )
    return bda.build(rows, REGISTRY, found, SOURCE)


def test_writing_the_areas_says_how_many_features_and_polygons_were_written(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    bda.write(_built(), ws)

    assert f"wrote {ws.areas} (1 features, 2 polygons, 0 kB)" in capsys.readouterr().out


def test_writing_the_areas_says_what_they_read_back_as(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    bda.write(_built(), ws)

    assert "reads back as 2 polygon(s): frr-x-mooring (2)" in capsys.readouterr().out


def test_writing_the_parts_says_how_many_are_assigned_and_unassigned(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    parts = _built().parts
    assert parts is not None

    bda.write_parts(ws.parts, parts)

    assert capsys.readouterr().out == (
        f"wrote {ws.parts} (3 features: 2 assigned, 1 unassigned, 1 kB)\n"
    )


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

    with pytest.raises(PipelineError):
        bda.run(ws, REGISTRY, [pbf], bda.Options(unassigned_ags=None))

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
    fc = json.loads(out.read_text(encoding="utf-8"))
    assert fc["properties"]["built_from"] == expected
    parts_fc = json.loads(parts_out.read_text(encoding="utf-8"))
    assert parts_fc["properties"]["built_from"] == expected
    # AreaIndex.from_geojson must keep working with the stamped file
    idx = dialect_areas.AreaIndex.from_geojson(str(out))
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


CLAIMED = {("w", 1), ("r", 100), ("w", 8)}  # the references of the district's area list


def _untimed(line: str) -> str:
    """A line of the scan's report, its time blanked."""
    return re.sub(r"\(\d+s\)", "(Ns)", line)


def test_a_scan_finds_each_claimed_reference_in_whichever_extract_holds_it(
    ws: Workspace,
) -> None:
    found = bda.scan(_write_district(ws), CLAIMED, "01054")

    assert set(found.claimed) == {("w", 1), ("r", 100), ("w", 8)}


def test_a_scan_finds_the_municipalities_of_the_district_that_no_row_claims(
    ws: Workspace,
) -> None:
    # not those of another district, of another admin level or no
    # administrative boundary, and not one whose ring is broken
    found = bda.scan(_write_district(ws), CLAIMED, "01054")

    assert {ref: m.name for ref, m in found.unclaimed.items()} == {
        ("r", 200): "Freetown",
        ("r", 300): "",
    }


def test_a_scan_without_a_district_finds_no_unclaimed_municipalities(ws: Workspace) -> None:
    found = bda.scan(_write_district(ws), CLAIMED, None)

    assert found.unclaimed == {}


def test_a_scan_has_the_ring_problems_of_the_claimed_areas_only(ws: Workspace) -> None:
    # Brokentown's broken ring is no problem: nobody claims it
    found = bda.scan(_write_district(ws), CLAIMED, "01054")

    assert found.problems == ["relation/100: 1 unclosed outer ring(s) -- skipped"]


def test_a_scan_says_what_an_extract_held(ws: Workspace) -> None:
    found = bda.scan(_write_district(ws), CLAIMED, "01054")

    assert _untimed(found.report[0]) == (
        "first.osm.pbf: 1/1 relations, 6 ways, 17 nodes, 3 unclaimed municipalities (Ns)"
    )


def test_a_later_extract_is_asked_only_for_what_the_earlier_ones_lacked(ws: Workspace) -> None:
    # Freetown, found in the first extract already, is not counted again
    found = bda.scan(_write_district(ws), CLAIMED, "01054")

    assert _untimed(found.report[1]) == "second.osm.pbf: 0/0 relations, 1 ways, 3 nodes (Ns)"


def test_the_parts_keep_their_schema(ws: Workspace) -> None:
    # municipalities a row claims and ones no row does
    bda.run(ws, REGISTRY, _write_district(ws))
    parts = json.loads(Path(ws.parts).read_text(encoding="utf-8"))
    assert schema_problems(parts, "dialect-area-parts") == []


def test_a_build_adds_the_municipalities_no_row_claims_to_the_parts(ws: Workspace) -> None:
    bda.run(ws, REGISTRY, _write_district(ws))
    parts = json.loads(Path(ws.parts).read_text(encoding="utf-8"))
    assert [f["properties"]["assigned"] for f in parts["features"]].count(False) == 2


def test_a_build_first_says_what_the_area_list_names(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    bda.run(ws, REGISTRY, _write_district(ws))

    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line == f"area list : {ws.area_list} -> 3 OSM objects, 2 dialects"


def test_a_build_without_the_parts_writes_none(ws: Workspace) -> None:
    pbf = _write_fixture(ws, "frr-x-mooring,way/1,Existing,\n")

    bda.run(ws, REGISTRY, [pbf], bda.Options(parts=False))

    assert not Path(ws.parts).exists()


def test_a_refused_build_has_listed_what_is_missing(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    first, _second = _write_district(ws)

    with pytest.raises(PipelineError):
        bda.run(ws, REGISTRY, [first])

    assert "  way/8  Second (frr-x-solring)" in capsys.readouterr().out.splitlines()


def test_a_refused_build_points_at_the_list_without_repeating_it(ws: Workspace) -> None:
    first, _second = _write_district(ws)

    with pytest.raises(PipelineError) as stop:
        bda.run(ws, REGISTRY, [first])

    assert str(stop.value) == (
        "1 object(s) of dialect_areas.csv not found in the extract(s), listed above -- "
        "run with --allow-missing to build anyway; nothing was written"
    )


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
