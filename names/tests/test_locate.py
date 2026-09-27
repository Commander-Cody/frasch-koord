"""names/locate.py: where each object of the name list is, worked out once
from the extract(s) into names/osm_objects.json, and which dialect is spoken
there -- the one answer the injector (tiles) and the search index share (#24)."""
from __future__ import annotations

import json

import pytest

import dialects
import locate
from conftest import places_text
from osm_fixture import ring, write_extract
from shapely.geometry import Point, Polygon

NAIBEL = 240042766


@pytest.fixture
def run_locate(world):
    """Locate the objects of `rows` in the extract(s) -> the objects file."""
    def run(rows, *extracts):
        (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
        out = world / "osm_objects.json"
        locate.main([*map(str, extracts), "--names", str(world / "places.csv"),
                     "--out", str(out)])
        return json.loads(out.read_text(encoding="utf-8"))
    return run


def test_a_node_is_where_it_is(run_locate, tmp_path):
    pbf = write_extract(tmp_path / "in.osm.pbf",
                        nodes={NAIBEL: ((8.8285, 54.7868), {"place": "town"})})
    objects = run_locate([{"kind": "settlement", "mooring": "Naibel",
                            "osm": f"node/{NAIBEL}"}], pbf)
    assert objects["objects"] == {f"node/{NAIBEL}": {"lon": 8.8285, "lat": 54.7868}}


# A U-shaped island: the mean of its corners (8.5, 54.5375) lies in the bay
# between the two arms, outside the island itself.
U_SHAPE = [(8.0, 54.0), (9.0, 54.0), (9.0, 55.0), (8.8, 55.0), (8.8, 54.2),
           (8.2, 54.2), (8.2, 55.0), (8.0, 55.0)]
U_WAY = 1000


def u_island(tmp_path, way_tags=None, relation=None):
    nodes, way_nodes = ring(1, *U_SHAPE)
    ways = {U_WAY: (way_nodes, way_tags or {"place": "island"})}
    relations = {relation[0]: ([("w", U_WAY, "outer")], relation[1])} if relation else {}
    return write_extract(tmp_path / "in.osm.pbf", nodes=nodes, ways=ways,
                         relations=relations)


def test_a_concave_island_is_located_inside_itself(run_locate, tmp_path):
    island = Polygon(U_SHAPE)
    assert not island.contains(Point(8.5, 54.5375))       # the vertex average
    objects = run_locate([{"kind": "island", "mooring": "U", "osm": f"way/{U_WAY}"}],
                         u_island(tmp_path))
    obj = objects["objects"][f"way/{U_WAY}"]
    assert island.contains(Point(obj["lon"], obj["lat"]))


def test_a_polygon_keeps_its_first_vertex_as_the_outline_point(run_locate, tmp_path):
    objects = run_locate([{"kind": "island", "mooring": "U", "osm": f"way/{U_WAY}"}],
                         u_island(tmp_path))
    assert objects["objects"][f"way/{U_WAY}"]["outline"] == [8.0, 54.0]


def test_an_administrative_area_records_its_level(run_locate, tmp_path):
    pbf = u_island(tmp_path, relation=(27019, {"type": "boundary",
                                               "boundary": "administrative",
                                               "admin_level": "6"}))
    objects = run_locate([{"kind": "landscape", "mooring": "Kris", "osm": "relation/27019"}],
                         pbf)
    assert objects["objects"]["relation/27019"]["admin_level"] == 6


def test_an_objects_low_saxon_name_is_recorded(run_locate, tmp_path):
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes={
        NAIBEL: ((8.8285, 54.7868), {"name": "Niebüll", "name:nds": "Niböl"})})
    objects = run_locate([{"kind": "settlement", "mooring": "Naibel",
                           "osm": f"node/{NAIBEL}"}], pbf)
    assert objects["objects"][f"node/{NAIBEL}"]["name_nds"] == "Niböl"


# --------------------------------------------------------------- dialect_at ---
def box(west, south, east, north):
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


@pytest.fixture
def areas(tmp_path):
    """Reußenköge (Mooring) with the Hamburger Hallig (Halligfriesisch)
    inside it, and a strip of Langeneß covering only part of Oland."""
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"dialect": tag},
         "geometry": {"type": "Polygon", "coordinates": box(*bounds)}}
        for tag, bounds in [("frr-x-mooring", (8.80, 54.55, 8.95, 54.63)),
                            ("frr-x-hallig", (8.82, 54.58, 8.86, 54.605)),
                            ("frr-x-hallig", (8.60, 54.60, 8.62, 54.62))]]}
    path = tmp_path / "areas.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return dialects.AreaIndex.from_geojson(str(path))


def test_the_smallest_area_around_an_object_wins(areas):
    assert locate.dialect_at({"lon": 8.84, "lat": 54.59}, areas) == "frr-x-hallig"


def test_outside_every_area_there_is_no_dialect(areas):
    assert locate.dialect_at({"lon": 8.0, "lat": 54.0}, areas) is None


def test_the_outline_point_answers_when_the_inside_point_misses(areas):
    oland = {"lon": 8.65, "lat": 54.61, "outline": [8.61, 54.61]}
    assert locate.dialect_at(oland, areas) == "frr-x-hallig"


def test_a_district_spans_dialects_and_gets_none(areas):
    kreis = {"lon": 8.84, "lat": 54.59, "admin_level": 6}
    assert locate.dialect_at(kreis, areas) is None


def test_a_municipality_gets_its_dialect(areas):
    gemeinde = {"lon": 8.84, "lat": 54.59, "admin_level": 8}
    assert locate.dialect_at(gemeinde, areas) == "frr-x-hallig"


# ------------------------------------------------------------ several files ---
def test_an_object_only_in_the_second_extract_is_found(run_locate, tmp_path):
    sh = write_extract(tmp_path / "schleswig-holstein-latest.osm.pbf",
                       nodes={NAIBEL: ((8.8285, 54.7868), {})})
    dk = write_extract(tmp_path / "denmark-latest.osm.pbf",
                       nodes={7: ((8.4, 55.4), {"name": "Fanø"})})
    objects = run_locate([{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"},
                          {"kind": "island", "mooring": "Fanø", "osm": "node/7"}], sh, dk)
    assert objects["objects"]["node/7"] == {"lon": 8.4, "lat": 55.4}


def test_the_file_records_the_extracts_it_was_read_from(run_locate, tmp_path):
    sh = write_extract(tmp_path / "schleswig-holstein-latest.osm.pbf",
                       nodes={NAIBEL: ((8.8285, 54.7868), {})},
                       timestamp="2026-09-22T20:22:59Z")
    objects = run_locate([{"kind": "settlement", "mooring": "Naibel",
                           "osm": f"node/{NAIBEL}"}], sh)
    assert objects["built_from"] == {"extracts": [
        {"file": "schleswig-holstein-latest.osm.pbf",
         "replication_timestamp": "2026-09-22T20:22:59Z"}]}


def test_the_file_reads_back_by_reference(run_locate, tmp_path):
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes={NAIBEL: ((8.8285, 54.7868), {})})
    run_locate([{"kind": "settlement", "mooring": "Naibel", "osm": f"node/{NAIBEL}"}], pbf)
    objects = locate.read_objects(str(tmp_path / "osm_objects.json"))
    assert objects.by_ref == {("n", NAIBEL): {"lon": 8.8285, "lat": 54.7868}}
    assert objects.built_from["extracts"][0]["file"] == "in.osm.pbf"


def test_a_relation_whose_label_node_the_extract_lacks_is_at_a_member_it_has(
        run_locate, tmp_path):
    # the North Sea: 216 member ways, a label node far offshore -- an extract
    # holds the relation, a couple of its coastline ways and not the label
    nodes, way_nodes = ring(1, (8.0, 54.0), (8.1, 54.0), (8.1, 54.1))
    pbf = write_extract(tmp_path / "in.osm.pbf", nodes=nodes,
                        ways={11: (way_nodes[:2], {})},
                        relations={9051063: ([("n", 7096172021, "label"),
                                              ("w", 10, "outer"), ("w", 11, "outer")],
                                             {"place": "sea"})})
    objects = run_locate([{"kind": "water", "mooring": "Weestsiie",
                           "osm": "relation/9051063"}], pbf)
    assert objects["objects"]["relation/9051063"] == {"lon": 8.0, "lat": 54.0}
