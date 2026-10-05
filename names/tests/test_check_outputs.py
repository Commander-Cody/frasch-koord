"""`frasch check-outputs` (`just check-outputs`, run in CI): are the committed
build outputs what their committed inputs give?  (#24: names.json was once
built from an uncommitted places.csv.)"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import build_dialect_areas, check_outputs, locate, provenance, registry, searchindex
from frasch.__main__ import main
from frasch.objects import Objects, objects_json
from frasch.paths import Workspace
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
AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"

# the `extract` fixture: the workspace, its extract, and the extract's nodes,
# ring way and relations
Extract = tuple[Workspace, Path, tuple[RingNodes, list[int], Relations]]


@pytest.fixture
def repo(ws: Workspace, world: Path) -> Workspace:
    """A workspace whose outputs are all up to date."""
    (world / "places.csv").write_text(places_text([NAIBEL]), encoding="utf-8")
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    stamp = {
        "dialect_areas.csv": provenance.blob_hash(world / "dialect_areas.csv"),
        "dialects.csv": provenance.blob_hash(world / "dialects.csv"),
        "extracts": [],
    }
    for name in ("dialect_areas.geojson", "dialect_areas_parts.geojson"):
        (world / name).write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": [], "properties": {"built_from": stamp}}
            ),
            encoding="utf-8",
        )
    (world / "osm_objects.json").write_text(
        objects_json(Objects({("n", 240042766): {"lon": 8.83, "lat": 54.79}}, {"extracts": []})),
        encoding="utf-8",
    )
    export(ws)
    return ws


def export(ws: Workspace) -> None:
    """Write the search index and the frontend's registry of `ws`, as the
    recipes would."""
    reg = registry.read(ws.dialects)
    searchindex.write(searchindex.build(ws, reg), ws.index)
    registry.export_json(reg, ws.registry_json)


def problems(ws: Workspace, *extracts: Path) -> str:
    """What the check finds wrong with `ws`, a line each."""
    found = check_outputs.problems(ws, registry.read(ws.dialects), [str(p) for p in extracts])
    return "\n".join(found)


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
    out = problems(repo)
    assert "dialect_areas.geojson" in out and "dialect_areas_parts.geojson" in out
    assert "just areas" in out


def test_dialect_areas_without_a_stamp_fail(repo: Workspace, world: Path) -> None:
    (world / "dialect_areas_parts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    out = problems(repo)
    assert "dialect_areas_parts.geojson" in out and "just areas" in out


def test_a_row_whose_object_was_never_located_fails(repo: Workspace, world: Path) -> None:
    (world / "places.csv").write_text(places_text([NAIBEL | {"osm": "node/99"}]), encoding="utf-8")
    assert "node/99" in problems(repo)


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
    out = problems(ws, pbf)
    assert "osm_objects.json" in out and "just objects" in out
    assert "dialect_areas.geojson" not in out


def test_an_area_that_moved_in_the_extract_fails(extract: Extract, world: Path) -> None:
    ws, pbf, (nodes, way, relations) = extract
    nodes[10] = ((8.7, 54.7), {})
    write_extract(pbf, nodes, {5: (way, {})}, relations)
    assert "dialect_areas.geojson" in problems(ws, pbf)


def test_each_file_is_rebuilt_from_the_extracts_its_stamp_names(
    extract: Extract, world: Path
) -> None:
    # the dialect areas come from the SH extract alone, the objects from SH + DK
    ws, pbf, _ = extract
    dk = write_extract(world / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    locate.run(ws, registry.read(ws.dialects), [pbf, dk])
    export(ws)
    assert problems(ws, pbf, dk) == ""


def test_an_extract_a_stamp_names_must_be_given(extract: Extract) -> None:
    ws, _pbf, _ = extract
    assert "in.osm.pbf" in problems(ws, Path("other.osm.pbf"))


def test_an_unstamped_file_names_no_extracts_to_rebuild_it_from(
    extract: Extract, world: Path
) -> None:
    ws, pbf, _ = extract
    (world / "dialect_areas.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    assert "dialect_areas.geojson names no extracts" in problems(ws, pbf)


def test_a_rows_second_object_never_located_fails(repo: Workspace, world: Path) -> None:
    # the search entry lies at the first object, but the tile build needs both
    (world / "places.csv").write_text(
        places_text([NAIBEL | {"osm": "node/240042766; node/99"}]), encoding="utf-8"
    )
    out = problems(repo)
    assert "naibel" in out and "node/99" in out and "just objects" in out


def test_the_command_fails_and_prints_what_is_wrong_with_the_files_its_options_name(
    repo: Workspace, world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (world / "places.csv").write_text(places_text([NAIBEL | {"osm": "node/99"}]), encoding="utf-8")
    files = ["names", "dialects", "curation", "area_list", "areas", "parts", "objects"]
    assert main(["check-outputs", *path_options(repo, *files, "index", "registry_json")]) == 1
    assert "  ! naibel: node/99 not in" in capsys.readouterr().out


def test_the_command_passes_up_to_date_outputs(
    repo: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    files = ["names", "dialects", "curation", "area_list", "areas", "parts", "objects"]
    assert main(["check-outputs", *path_options(repo, *files, "index", "registry_json")]) == 0
    assert capsys.readouterr().out == "the committed build outputs match their inputs\n"
