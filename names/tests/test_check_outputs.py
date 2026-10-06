"""`frasch check-outputs` (`just check-outputs`, run in CI): are the committed
build outputs what their committed inputs give?  (#24: names.json was once
built from an uncommitted places.csv.)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import build_dialect_areas, check_outputs, locate, match, osmscan, registry
from frasch import searchindex
from frasch.__main__ import main
from frasch.objects import Objects, objects_json
from frasch.paths import Workspace
from frasch.pipeline import Extracts, Run
from frasch.provenance import Stamp
from conftest import REGISTRY_CSV, path_options, places_text
from osm_fixture import Relations, RingNodes, ring, write_extract

NAIBEL = {
    "id": "naibel",
    "kind": "settlement",
    "mooring": "Naibel",
    "de": "Niebüll",
    "osm": "node/240042766",
    "status": "ok",
}
NAIBEL_NODE = ("n", 240042766)
AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"

# the `extract` fixture: the workspace, its extract, and the extract's nodes,
# ring way and relations
Extract = tuple[Workspace, Path, tuple[RingNodes, list[int], Relations]]


@pytest.fixture
def repo(ws: Workspace, world: Path) -> Workspace:
    """A workspace whose outputs are all up to date."""
    (world / "places.csv").write_text(places_text([NAIBEL]), encoding="utf-8")
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    stamp = build_dialect_areas.stamp(ws, []).as_json()
    for name in ("dialect_areas.geojson", "dialect_areas_parts.geojson"):
        (world / name).write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": [], "properties": {"built_from": stamp}}
            ),
            encoding="utf-8",
        )
    write_objects(ws, Objects({NAIBEL_NODE: {"lon": 8.83, "lat": 54.79}}, Stamp({}, [])))
    write_report(ws)
    export(ws)
    return ws


def write_objects(ws: Workspace, objects: Objects) -> None:
    Path(ws.objects).write_text(objects_json(objects), encoding="utf-8")


def write_report(ws: Workspace, *extracts: Path) -> None:
    """Write a report stamped as the matcher would stamp it now, with
    candidates from `extracts`."""
    stamp = match.stamp(ws, osmscan.extract_stamps(extracts))
    Path(ws.report).write_text(
        f"# Name matching report\n\n{stamp.as_comment()}\n", encoding="utf-8"
    )


def export(ws: Workspace) -> None:
    """Write the search index and the frontend's registry of `ws`, as the
    recipes would."""
    reg = registry.read(ws.dialects)
    searchindex.write(searchindex.build(ws, reg), ws.index)
    registry.export_json(reg, ws.registry_json)


def problems(ws: Workspace, *extracts: Path) -> str:
    """What the check finds wrong with `ws`, a line each."""
    given = Extracts.given([str(p) for p in extracts])
    return "\n".join(check_outputs.problems(Run(ws, registry.read(ws.dialects), given)))


def test_up_to_date_outputs_pass(repo: Workspace) -> None:
    assert problems(repo) == ""


def test_an_index_built_from_another_name_list_fails(repo: Workspace, world: Path) -> None:
    (world / "places.csv").write_text(
        places_text([NAIBEL | {"mooring": "Naibel;Niebel"}]), encoding="utf-8"
    )
    assert "names.json" in problems(repo)


def test_a_registry_edit_without_an_export_fails(repo: Workspace, world: Path) -> None:
    registry = world / "dialects.csv"
    text = registry.read_text(encoding="utf-8")
    registry.write_text(text.replace(",Mooring,", ",Mooring (edited),", 1), encoding="utf-8")
    assert "dialects.json" in problems(repo)


def test_dialect_areas_built_from_another_area_list_fail(repo: Workspace, world: Path) -> None:
    (world / "dialect_areas.csv").write_text(
        AREA_LIST + "frr-x-fering,Wyk,relation/2,\n", encoding="utf-8"
    )
    assert problems(repo) == (
        f"{repo.areas} was not built from the current dialect_areas.csv "
        "-- rebuild it with `just rebuild areas`"
    )


def test_dialect_areas_without_a_stamp_fail(repo: Workspace, world: Path) -> None:
    (world / "dialect_areas_parts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    assert f"{repo.parts} was not built from the current dialect_areas.csv" in problems(repo)


def test_a_report_written_from_another_name_list_fails(repo: Workspace, world: Path) -> None:
    (world / "places.csv").write_text(
        places_text([NAIBEL | {"de": "Niebüll; Naibel"}]), encoding="utf-8"
    )
    export(repo)
    assert problems(repo) == (
        f"{repo.report} was not built from the current places.csv "
        "-- rebuild it with `just rebuild report`"
    )


def test_a_row_whose_object_was_never_located_fails(repo: Workspace, world: Path) -> None:
    (world / "places.csv").write_text(places_text([NAIBEL | {"osm": "node/99"}]), encoding="utf-8")
    assert "naibel (line 2): node/99 is not located yet" in problems(repo)


def test_objects_of_a_row_that_went_off_the_map_fail(repo: Workspace, world: Path) -> None:
    (world / "places.csv").write_text(places_text([NAIBEL | {"status": "skip"}]), encoding="utf-8")
    write_report(repo)
    export(repo)
    assert problems(repo) == (
        f"{repo.objects} was located for other references than the rows on the map name now "
        "(1 no longer named) -- rebuild it with `just rebuild objects`"
    )


def test_a_reference_no_extract_holds_fails_with_what_helps(repo: Workspace, world: Path) -> None:
    # the search entry lies at the first object, but the tile build needs both
    (world / "places.csv").write_text(
        places_text([NAIBEL | {"osm": "node/240042766; node/99"}]), encoding="utf-8"
    )
    in_vain = frozenset({("n", 99)})
    write_objects(repo, Objects({NAIBEL_NODE: {"lon": 8.83, "lat": 54.79}}, Stamp({}, []), in_vain))
    write_report(repo)
    export(repo)
    assert problems(repo) == (
        "naibel (line 2): node/99 is in none of the extracts -- correct the `osm` cell of its row"
    )


# -------------------------------------------------------- --extracts (full) ---
@pytest.fixture
def extract(world: Path, repo: Workspace) -> Extract:
    """An extract the committed objects file and dialect areas were really
    built from; -> (the workspace, the extract, the extract's content)."""
    nodes, way = ring(10, (8.8, 54.7), (8.9, 54.7), (8.9, 54.8), (8.8, 54.8))
    nodes[240042766] = ((8.83, 54.79), {})
    relations: Relations = {1: ([("w", 5, "outer")], {"boundary": "administrative"})}
    pbf = write_extract(world / "in.osm.pbf", nodes, {5: (way, {})}, relations)
    build_from_extract(repo, pbf)
    return repo, pbf, (nodes, way, relations)


def build_from_extract(ws: Workspace, pbf: Path) -> None:
    """Rebuild every output of `ws` from `pbf`, as the recipes would."""
    reg = registry.read(ws.dialects)
    locate.run(ws, reg, [pbf])
    build_dialect_areas.run(ws, reg, [pbf])
    write_report(ws, pbf)
    export(ws)


def test_outputs_the_extract_really_gives_pass(extract: Extract) -> None:
    ws, pbf, _ = extract
    assert problems(ws, pbf) == ""


def test_the_objects_are_rebuilt_with_the_registry_passed_in(extract: Extract, world: Path) -> None:
    # Naibel is named only in a dialect of world's own registry, so only a
    # rebuild that reads places.csv with that registry puts it on the map
    ws, pbf, _ = extract
    (world / "dialects.csv").write_text(
        REGISTRY_CSV + "frr-x-strand,strand,Strander,extinct,no,\n", encoding="utf-8"
    )
    header, row, _ = places_text([NAIBEL | {"mooring": ""}]).split("\n")
    (world / "places.csv").write_text(f"{header},strand\n{row},Naibel\n", encoding="utf-8")
    build_from_extract(ws, pbf)
    assert problems(ws, pbf) == ""


def test_an_object_that_moved_in_the_extract_fails(extract: Extract, world: Path) -> None:
    ws, pbf, (nodes, way, relations) = extract
    nodes[240042766] = ((8.84, 54.79), {})
    write_extract(pbf, nodes, {5: (way, {})}, relations)
    assert problems(ws, pbf) == (
        f"{ws.objects} is not what its inputs give -- rebuild it with `just rebuild objects`"
    )


def test_an_area_that_moved_in_the_extract_fails(extract: Extract, world: Path) -> None:
    ws, pbf, (nodes, way, relations) = extract
    nodes[10] = ((8.7, 54.7), {})
    write_extract(pbf, nodes, {5: (way, {})}, relations)
    assert "dialect_areas.geojson" in problems(ws, pbf)


def test_a_rebuild_that_cannot_run_says_why(extract: Extract, world: Path) -> None:
    # the extract lost the relation the area list names
    ws, pbf, (nodes, way, _relations) = extract
    write_extract(pbf, nodes, {5: (way, {})})
    assert f"{ws.areas} cannot be rebuilt: no geometry found" in problems(ws, pbf)


def test_the_dialect_areas_are_rebuilt_from_the_first_extract_alone(
    extract: Extract, world: Path
) -> None:
    # the dialect areas come from the SH extract alone, the objects from SH + DK
    ws, pbf, _ = extract
    dk = write_extract(world / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    locate.run(ws, registry.read(ws.dialects), [pbf, dk])
    write_report(ws, pbf, dk)
    export(ws)
    assert problems(ws, pbf, dk) == ""


def test_outputs_built_from_other_extracts_than_the_given_ones_fail(
    extract: Extract, world: Path
) -> None:
    ws, _pbf, _ = extract
    other = write_extract(world / "other.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    assert f"{ws.objects} was not built from the current extracts" in problems(ws, other)


# every path option of the command
FILES = ["names", "dialects", "curation", "area_list", "areas", "parts", "objects"]
FILES += ["report", "index", "registry_json"]


def test_the_command_fails_and_prints_what_is_wrong_with_the_files_its_options_name(
    repo: Workspace, world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (world / "places.csv").write_text(places_text([NAIBEL | {"osm": "node/99"}]), encoding="utf-8")
    assert main(["check-outputs", *path_options(repo, *FILES)]) == 1
    assert "  ! naibel (line 2): node/99 is not located yet" in capsys.readouterr().out


def test_the_command_passes_up_to_date_outputs(
    repo: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check-outputs", *path_options(repo, *FILES)]) == 0
    assert capsys.readouterr().out == "the committed build outputs match their inputs\n"
