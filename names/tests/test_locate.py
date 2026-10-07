"""`frasch build objects`: where each object of the name list is, worked out once
from the extract(s) into names/osm_objects.json -- the one answer the
injector (tiles) and the search index share (#24)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

import pytest

from frasch import locate
from frasch.__main__ import main
from frasch.objects import read_objects
from conftest import REGISTRY, REGISTRY_CSV, path_options, places_text, workspace
from osm_fixture import ring, write_extract
from shapely.geometry import Point, Polygon

NAIBEL = 240042766


class RunLocate(Protocol):
    def __call__(self, rows: Iterable[Mapping[str, str]], *extracts: Path) -> Any: ...


@pytest.fixture
def run_locate(world: Path) -> RunLocate:
    """Locate the objects of `rows` in the extract(s) -> the objects file."""

    def run(rows: Iterable[Mapping[str, str]], *extracts: Path) -> Any:
        (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
        locate.run(workspace(world), REGISTRY, extracts)
        return json.loads((world / "osm_objects.json").read_text(encoding="utf-8"))

    return run


def test_a_node_is_where_it_is(run_locate: RunLocate, tmp_path: Path) -> None:
    pbf = write_extract(
        tmp_path / "in.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {"place": "town"})}
    )
    objects = run_locate(
        [{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"}], pbf
    )
    assert objects["objects"] == {f"node/{NAIBEL}": {"lon": 8.8285, "lat": 54.7868}}


# A U-shaped island: the mean of its corners (8.5, 54.5375) lies in the bay
# between the two arms, outside the island itself.
U_SHAPE = [
    (8.0, 54.0),
    (9.0, 54.0),
    (9.0, 55.0),
    (8.8, 55.0),
    (8.8, 54.2),
    (8.2, 54.2),
    (8.2, 55.0),
    (8.0, 55.0),
]
U_WAY = 1000


def u_island(
    tmp_path: Path,
    way_tags: dict[str, str] | None = None,
    relation: tuple[int, dict[str, str]] | None = None,
) -> Path:
    nodes, way_nodes = ring(1, *U_SHAPE)
    ways = {U_WAY: (way_nodes, way_tags or {"place": "island"})}
    relations = {relation[0]: ([("w", U_WAY, "outer")], relation[1])} if relation else {}
    return write_extract(tmp_path / "in.osm.pbf", nodes=nodes, ways=ways, relations=relations)


def test_a_concave_island_is_located_inside_itself(run_locate: RunLocate, tmp_path: Path) -> None:
    island = Polygon(U_SHAPE)
    assert not island.contains(Point(8.5, 54.5375))  # the vertex average
    objects = run_locate(
        [{"kind": "island", "mooring": "U", "osm": f"way/{U_WAY}"}], u_island(tmp_path)
    )
    obj = objects["objects"][f"way/{U_WAY}"]
    assert island.contains(Point(obj["lon"], obj["lat"]))


def test_a_polygon_keeps_its_first_vertex_as_the_outline_point(
    run_locate: RunLocate, tmp_path: Path
) -> None:
    objects = run_locate(
        [{"kind": "island", "mooring": "U", "osm": f"way/{U_WAY}"}], u_island(tmp_path)
    )
    assert objects["objects"][f"way/{U_WAY}"]["outline"] == [8.0, 54.0]


def test_an_administrative_area_records_its_level(run_locate: RunLocate, tmp_path: Path) -> None:
    pbf = u_island(
        tmp_path,
        relation=(27019, {"type": "boundary", "boundary": "administrative", "admin_level": "6"}),
    )
    objects = run_locate([{"kind": "landscape", "mooring": "Kris", "osm": "relation/27019"}], pbf)
    assert objects["objects"]["relation/27019"]["admin_level"] == 6


def test_an_objects_low_saxon_name_is_recorded(run_locate: RunLocate, tmp_path: Path) -> None:
    pbf = write_extract(
        tmp_path / "in.osm.pbf",
        nodes={NAIBEL: ((8.8285, 54.7868), {"name": "Niebüll", "name:nds": "Niböl"})},
    )
    objects = run_locate(
        [{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"}], pbf
    )
    assert objects["objects"][f"node/{NAIBEL}"]["name_nds"] == "Niböl"


def test_an_objects_frisian_name_is_recorded(run_locate: RunLocate, tmp_path: Path) -> None:
    husum = 240085119
    pbf = write_extract(
        tmp_path / "in.osm.pbf",
        nodes={husum: ((9.0510, 54.4764), {"name": "Husum", "name:frr": "Hüsem"})},
    )
    objects = run_locate([{"kind": "settlement", "mooring": "Hüsem", "osm": f"node/{husum}"}], pbf)
    assert objects["objects"][f"node/{husum}"]["name_frr"] == "Hüsem"


def test_an_objects_generic_name_is_recorded(run_locate: RunLocate, tmp_path: Path) -> None:
    ribe = 597643755
    pbf = write_extract(
        tmp_path / "in.osm.pbf",
        nodes={ribe: ((8.7632, 55.3281), {"name": "Ribe", "name:de": "Ripen"})},
    )
    objects = run_locate(
        [{"kind": "settlement", "mooring": "Ripen", "de": "Ripen", "osm": f"node/{ribe}"}], pbf
    )
    assert objects["objects"][f"node/{ribe}"]["name"] == "Ribe"


# ------------------------------------------------------------ several files ---
def test_an_object_only_in_the_second_extract_is_found(
    run_locate: RunLocate, tmp_path: Path
) -> None:
    sh = write_extract(
        tmp_path / "schleswig-holstein-latest.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {})}
    )
    dk = write_extract(
        tmp_path / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {"name": "Fanø"})}
    )
    objects = run_locate(
        [
            {"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"},
            {"kind": "island", "mooring": "Fanø", "osm": "node/7"},
        ],
        sh,
        dk,
    )
    assert objects["objects"]["node/7"] == {"lon": 8.4, "lat": 55.4, "name": "Fanø"}


def test_the_file_records_the_extracts_it_was_read_from(
    run_locate: RunLocate, tmp_path: Path
) -> None:
    sh = write_extract(
        tmp_path / "schleswig-holstein-latest.osm.pbf",
        nodes={NAIBEL: ((8.8285, 54.7868), {})},
        timestamp="2026-09-22T20:22:59Z",
    )
    objects = run_locate([{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"}], sh)
    assert objects["built_from"] == {
        "extracts": [
            {
                "file": "schleswig-holstein-latest.osm.pbf",
                "replication_timestamp": "2026-09-22T20:22:59Z",
            }
        ]
    }


def test_the_file_reads_back_by_reference(
    run_locate: RunLocate, world: Path, tmp_path: Path
) -> None:
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {})})
    run_locate([{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"}], pbf)
    objects = read_objects(str(world / "osm_objects.json"))
    assert objects.by_ref == {("n", NAIBEL): {"lon": 8.8285, "lat": 54.7868}}
    assert objects.stamp.extracts == [{"file": "in.osm.pbf", "replication_timestamp": ""}]


def test_the_command_locates_the_rows_the_registry_of_its_option_puts_on_the_map(
    world: Path, tmp_path: Path
) -> None:
    # `--dialects`: a row named only in a dialect of that registry is located
    registry = tmp_path / "other-dialects.csv"
    registry.write_text(
        REGISTRY_CSV + "frr-x-strand,strand,Strander,extinct,no,\n", encoding="utf-8"
    )
    header, row, _ = places_text([{"kind": "island", "osm": f"node/{NAIBEL}"}]).split("\n")
    (world / "places.csv").write_text(f"{header},strand\n{row},Strand\n", encoding="utf-8")
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {})})
    files = path_options(workspace(world), "names", "objects")
    assert main(["build", "objects", str(pbf), *files, "--dialects", str(registry)]) == 0
    objects = json.loads((world / "osm_objects.json").read_text(encoding="utf-8"))
    assert objects["objects"] == {f"node/{NAIBEL}": {"lon": 8.8285, "lat": 54.7868}}


def test_a_relation_whose_label_node_the_extract_lacks_is_at_a_member_it_has(
    run_locate: RunLocate, tmp_path: Path
) -> None:
    # the North Sea: 216 member ways, a label node far offshore -- an extract
    # holds the relation, a couple of its coastline ways and not the label
    nodes, way_nodes = ring(1, (8.0, 54.0), (8.1, 54.0), (8.1, 54.1))
    pbf = write_extract(
        tmp_path / "in.osm.pbf",
        nodes=nodes,
        ways={11: (way_nodes[:2], {})},
        relations={
            9051063: (
                [("n", 7096172021, "label"), ("w", 10, "outer"), ("w", 11, "outer")],
                {"place": "sea"},
            )
        },
    )
    objects = run_locate(
        [{"kind": "water", "mooring": "Weestsiie", "osm": "relation/9051063"}], pbf
    )
    assert objects["objects"]["relation/9051063"] == {"lon": 8.0, "lat": 54.0}


def test_a_reference_no_extract_holds_is_recorded_as_not_found(
    run_locate: RunLocate, tmp_path: Path
) -> None:
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {})})
    rows = [{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}; way/99"}]
    assert run_locate(rows, pbf)["not_found"] == ["way/99"]
