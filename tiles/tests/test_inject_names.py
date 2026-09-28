"""inject_names.py: reading the curation file, the tags an object gets, and a
whole `run()` over a tiny extract written here with pyosmium.

The extract mirrors real places (ids and positions from the
Schleswig-Holstein extract; ring nodes made up): the village Holm, the
Nordwarft way on Ockholm, the Hamburger Hallig relation, the Nordstrand
village node that carries the synthetic island square, Tammensiel (curated,
not in the name list), and Westerheide on Amrum, a place OSM does not have."""
from __future__ import annotations

import csv
import io
import json
import math

import osmium
import pytest

from frasch import paths, registry
from frasch.errors import PipelineError, ValidationError
from frasch import inject_names
from frasch import locate
from frasch import placelist


# ------------------------------------------------------------- square_around ---
def test_square_at_the_equator():
    # 4 km² -> 1 km from the centre to each side; 1 km = 1/111.32 degree
    d = 1 / 111.32
    corners = inject_names.square_around(0.0, 0.0, 4.0)
    assert corners == pytest.approx([(-d, -d), (d, -d), (d, d), (-d, d)])


def test_square_at_sixty_degrees_is_twice_as_wide_in_longitude():
    # cos 60° = 1/2: a kilometre spans twice the degrees of longitude
    d = 1 / 111.32
    (w, s), (e, _), (_, n), _ = inject_names.square_around(8.0, 60.0, 4.0)
    assert (w, e) == pytest.approx((8.0 - 2 * d, 8.0 + 2 * d))
    assert (s, n) == pytest.approx((60.0 - d, 60.0 + d))


def test_square_is_centred_on_the_node():
    # Planetiler labels a polygon at its interior point: that must be the node
    corners = inject_names.square_around(8.865286, 54.487378, 50.0)
    assert sum(x for x, _ in corners) / 4 == pytest.approx(8.865286)
    assert sum(y for _, y in corners) / 4 == pytest.approx(54.487378)


# ----------------------------------------------------------------- name_tags ---
@pytest.fixture(scope="module")
def reg():
    return registry.read()


def place(line=2, **cells):
    r = {c: "" for c in placelist.columns()}
    r.update(cells, _line=line)
    return r


BRODERSWARFT = place(id="brouderswarw", kind="warft", mooring="Brouderswärw",
                     local="Brouersweerw (Foortuftinge)", de="Broderswarft",
                     osm="node/1594721085")


def test_name_tags_of_a_row_with_a_local_variety(reg):
    assert inject_names.name_tags([BRODERSWARFT], "frr-x-mooring", reg) == {
        "name:frr-x-mooring": "Brouderswärw",
        "frasch:kind": "warft",
        "frasch:dialect": "frr-x-mooring",
        "frasch:local": "Brouersweerw",
        "frasch:variety": "Foortuftinge",
        "frasch:ref": "brouderswarw",
    }


def test_name_tags_fill_the_areas_dialect_from_local(reg):
    tags = inject_names.name_tags([BRODERSWARFT], "frr-x-nordgoes", reg)
    assert tags["name:frr-x-nordgoes"] == "Brouersweerw"


def test_name_tags_outside_any_area_have_no_dialect(reg):
    hanswarft = place(id="hanswarw", kind="warft", mooring="Hanswärw", hallig="Hansweerf",
                      de="Hanswarft", osm="node/3410324993")
    assert inject_names.name_tags([hanswarft], None, reg) == {
        "name:frr-x-mooring": "Hanswärw",
        "name:frr-x-hallig": "Hansweerf",
        "frasch:kind": "warft",
        "frasch:ref": "hanswarw",
    }


def test_name_tags_first_row_wins_per_tag(reg):
    # two rows claim one object: the first in file order keeps its names,
    # the second only fills what the first leaves empty
    first = place(2, id="hulm", kind="settlement", mooring="Hulm", de="Holm",
                  osm="node/240102263")
    second = place(9, id="hulm-gutskuuch", kind="koog", mooring="Hulm Gutskuuch", wieding="Hoolm",
                   de="Holm", osm="node/240102263")
    tags = inject_names.name_tags([first, second], None, reg)
    assert tags["name:frr-x-mooring"] == "Hulm"
    assert tags["name:frr-x-wieding"] == "Hoolm"
    assert tags["frasch:kind"] == "settlement"
    assert tags["frasch:ref"] == "hulm"


def test_name_tags_refer_to_the_rows_id(reg):
    # not to the object: the search index names the place by the row (#23)
    denmark = place(id="daanemark", kind="country", mooring="Däänemark",
                    de="Dänemark", wikidata="Q35")
    assert inject_names.name_tags([denmark], None, reg)["frasch:ref"] == "daanemark"


# ------------------------------------------------------------- load_curation ---
CURATION_HEADER = ["osm", "name", "lat", "lon", "set_tags", "minzoom", "maxzoom",
                   "polygon_km2", "note"]


def curation_file(tmp_path, *rows):
    path = tmp_path / "curation.csv"
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=CURATION_HEADER, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in CURATION_HEADER})
    path.write_text(buf.getvalue(), encoding="utf-8")
    return str(path)


def test_curation_row_tags_an_osm_object(tmp_path):
    path = curation_file(tmp_path, {"osm": "way/177387348", "name": "Habel",
                                    "set_tags": "place=island"})
    by_id, synthetic, points = inject_names.load_curation(path)
    assert by_id == {("w", 177387348): {"tags": {"place": "island"}, "label": "Habel"}}
    assert synthetic == {} and points == {}


def test_curation_zooms_become_string_tags(tmp_path):
    path = curation_file(tmp_path, {"osm": "node/355956234", "name": "Tammensiel",
                                    "minzoom": "10", "maxzoom": "12"})
    by_id, _, _ = inject_names.load_curation(path)
    assert by_id[("n", 355956234)]["tags"] == {"frasch:minzoom": "10",
                                               "frasch:maxzoom": "12"}


def test_curation_row_with_several_objects_tags_each(tmp_path):
    path = curation_file(tmp_path, {"osm": "way/44051131; way/44051132",
                                    "name": "Arlau",
                                    "set_tags": "name:frr-x-mooring=Arlou"})
    by_id, _, _ = inject_names.load_curation(path)
    assert set(by_id) == {("w", 44051131), ("w", 44051132)}
    assert by_id[("w", 44051132)]["tags"] == {"name:frr-x-mooring": "Arlou"}


def test_curation_row_with_nothing_to_apply_is_skipped(tmp_path):
    path = curation_file(tmp_path, {"osm": "node/1", "name": "just a note",
                                    "note": "look at this later"})
    assert inject_names.load_curation(path) == ({}, {}, {})


def test_polygon_km2_row_describes_a_square_not_a_tag_change(tmp_path):
    path = curation_file(tmp_path, {"osm": "node/85929111", "name": "Nordstrand",
                                    "set_tags": "place=island", "maxzoom": "11",
                                    "polygon_km2": "50"})
    by_id, synthetic, _ = inject_names.load_curation(path)
    assert by_id == {}
    assert synthetic == {("n", 85929111): {
        "km2": 50.0, "tags": {"place": "island", "frasch:maxzoom": "11"},
        "label": "Nordstrand"}}


def test_local_reference_row_positions_a_place(tmp_path):
    path = curation_file(tmp_path, {"osm": "local/westerheide-amrum",
                                    "name": "Westerheide (Amrum)",
                                    "lat": "54.65097", "lon": "8.34019"})
    _, _, points = inject_names.load_curation(path)
    p = points[("l", "westerheide-amrum")]
    assert (p["lon"], p["lat"], p["km2"], p["tags"]) == (8.34019, 54.65097, None, {})


def test_missing_curation_file_is_nothing_curated(tmp_path):
    assert inject_names.load_curation(str(tmp_path / "absent.csv")) == ({}, {}, {})


def test_missing_curation_file_named_explicitly_stops(tmp_path):
    with pytest.raises(PipelineError, match="not found"):
        inject_names.load_curation(str(tmp_path / "absent.csv"), required=True)


@pytest.mark.parametrize("bad,message", [
    ({"osm": "node/85929111", "lat": "54.48", "lon": "8.86"}, "only go with a local"),
    ({"osm": "local/westerheide-amrum"}, "needs `lat` and `lon`"),
    ({"osm": "node/355956234", "minzoom": "ten"}, "not an integer"),
    ({"osm": "node/85929111", "polygon_km2": "0"}, "not a positive number"),
    ({"osm": "node/85929111", "polygon_km2": "fifty"}, "not a positive number"),
    ({"osm": "way/177387348", "polygon_km2": "5"}, "exactly one node"),
    ({"osm": "node/1; node/2", "polygon_km2": "5"}, "exactly one node"),
])
def test_bad_curation_row_stops_the_build(tmp_path, bad, message):
    with pytest.raises(ValidationError, match=message):
        inject_names.load_curation(curation_file(tmp_path, bad))


def test_second_row_for_one_local_reference_stops_the_build(tmp_path):
    row = {"osm": "local/huelltoft", "lat": "54.881287", "lon": "8.771304"}
    with pytest.raises(ValidationError, match="second row"):
        inject_names.load_curation(curation_file(tmp_path, row, row))


def test_second_polygon_for_one_node_stops_the_build(tmp_path):
    row = {"osm": "node/85929111", "polygon_km2": "50"}
    with pytest.raises(ValidationError, match="second polygon_km2"):
        inject_names.load_curation(curation_file(tmp_path, row, row))


# ------------------------------------------------------------ a whole run() ---
HOLM = 240102263
NORDSTRAND = 85929111
TAMMENSIEL = 355956234
UNTOUCHED_NODE = 240000001
NORDWARFT = 1347936331
HALLIG_RING = 500000001
UNTOUCHED_WAY = 600000001
HAMBURGER_HALLIG = 5615880
KREIS = 27019

# closed rings: the Nordwarft on Ockholm, the Hamburger Hallig's outline
NORDWARFT_NODES = {9000000001: (8.826, 54.668), 9000000002: (8.830, 54.668),
                   9000000003: (8.830, 54.671), 9000000004: (8.826, 54.671)}
HALLIG_NODES = {9100000001: (8.825, 54.585), 9100000002: (8.850, 54.585),
                9100000003: (8.850, 54.600), 9100000004: (8.825, 54.600)}
MAX_NODE = 9100000004
MAX_WAY = NORDWARFT

PLACES = [
    dict(id="hulm", kind="settlement", mooring="Hulm", de="Holm", osm=f"node/{HOLM}",
         wikidata="Q559369", status="ok"),
    dict(id="nordwarw", kind="warft", mooring="Nordwärw", nordgoes="Noordweerw", de="Nordwarft",
         hint="Ockholm", osm=f"way/{NORDWARFT}", status="ok"),
    dict(id="hamborjer-hali", kind="hallig", mooring="Hamborjer Håli", de="Hamburger Hallig",
         osm=f"relation/{HAMBURGER_HALLIG}", status="ok"),
    # the Kreis relation runs along the Hallig's outline here: a district
    # around a Hallig, so its inside point lies in the Hallig's area
    dict(id="kris", kind="landscape", mooring="Kris Nordfraschlönj",
         nordgoes="Noordfräischloun Krais", de="Kreis Nordfriesland",
         osm=f"relation/{KREIS}", status="ok"),
    dict(id="waasterhias", kind="settlement", oomrang="Waasterhias", de="Westerheide",
         osm="local/westerheide-amrum", status="ok"),
]

CURATION = [
    {"osm": f"node/{NORDSTRAND}", "name": "Nordstrand (synthetic island polygon)",
     "set_tags": "place=island;frasch:kind=island", "maxzoom": "11",
     "polygon_km2": "50"},
    {"osm": f"node/{NORDSTRAND}", "name": "Nordstrand (village node)",
     "set_tags": "name:frr-x-mooring=e Strönj;frasch:ref=relation/1420555",
     "minzoom": "12"},
    {"osm": f"node/{TAMMENSIEL}", "name": "Tammensiel", "minzoom": "10"},
    {"osm": f"relation/{HAMBURGER_HALLIG}", "name": "Hamburger Hallig",
     "set_tags": "place=island", "minzoom": "12"},
    {"osm": "local/westerheide-amrum", "name": "Westerheide (Amrum)",
     "lat": "54.65097", "lon": "8.34019"},
]


def box(west, south, east, north):
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


# Amrum; Ockholm (Nordergoesharde); Reußenköge (Mooring) with the Hamburger
# Hallig (Halligfriesisch) inside it -- the smaller area must win
AREAS = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"dialect": tag},
     "geometry": {"type": "Polygon", "coordinates": box(*bounds)}}
    for tag, bounds in [
        ("frr-x-oomrang", (8.30, 54.62, 8.40, 54.70)),
        ("frr-x-nordgoes", (8.78, 54.64, 8.90, 54.70)),
        ("frr-x-mooring", (8.80, 54.55, 8.95, 54.63)),
        ("frr-x-hallig", (8.82, 54.58, 8.86, 54.605)),
    ]]}


def write_extract(path):
    Node, Way, Relation = (osmium.osm.mutable.Node, osmium.osm.mutable.Way,
                           osmium.osm.mutable.Relation)
    nodes = {
        NORDSTRAND: ((8.865286, 54.487378), {"place": "village", "name": "Nordstrand"}),
        HOLM: ((8.866668, 54.833305), {"place": "village", "name": "Holm",
                                       "wikidata": "Q559369"}),
        UNTOUCHED_NODE: ((8.9, 54.6), {"place": "village", "name": "Bredstedt"}),
        TAMMENSIEL: ((8.7033, 54.7433), {"place": "hamlet", "name": "Tammensiel"}),
    }
    nodes.update({i: (loc, {}) for i, loc in NORDWARFT_NODES.items()})
    nodes.update({i: (loc, {}) for i, loc in HALLIG_NODES.items()})
    w = osmium.SimpleWriter(str(path))
    try:
        for nid in sorted(nodes):
            loc, tags = nodes[nid]
            w.add_node(Node(id=nid, version=1, visible=True, location=loc, tags=tags))
        # ways in ascending id order, like any extract
        ring = list(HALLIG_NODES)
        w.add_way(Way(id=HALLIG_RING, version=1, visible=True, nodes=ring + ring[:1],
                      tags={"natural": "coastline"}))
        w.add_way(Way(id=UNTOUCHED_WAY, version=1, visible=True,
                      nodes=[NORDSTRAND, HOLM], tags={"highway": "track"}))
        ring = list(NORDWARFT_NODES)
        w.add_way(Way(id=NORDWARFT, version=1, visible=True, nodes=ring + ring[:1],
                      tags={"name": "Nordwarft", "landuse": "residential"}))
        w.add_relation(Relation(
            id=KREIS, version=1, visible=True,
            members=[("w", HALLIG_RING, "outer")],
            tags={"type": "boundary", "boundary": "administrative",
                  "admin_level": "6", "name": "Kreis Nordfriesland"}))
        w.add_relation(Relation(
            id=HAMBURGER_HALLIG, version=1, visible=True,
            members=[("w", HALLIG_RING, "outer")],
            tags={"type": "boundary", "boundary": "administrative",
                  "admin_level": "10", "name": "Hamburger Hallig"}))
    finally:
        w.close()


def read_extract(path):
    """-> [(type letter, id, tags, extra)] in file order; `extra` is a
    node's (lon, lat) or a way's node ids."""
    out = []
    for o in osmium.FileProcessor(str(path)):
        t = o.type_str()
        extra = ((o.location.lon, o.location.lat) if t == "n"
                 else [n.ref for n in o.nodes] if t == "w" else None)
        out.append((t, o.id, dict(o.tags), extra))
    return out


def places_csv(rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=placelist.columns(), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in placelist.columns()})
    return buf.getvalue()


@pytest.fixture(scope="module")
def injected(tmp_path_factory):
    d = tmp_path_factory.mktemp("inject")
    (d / "places.csv").write_text(places_csv(PLACES), encoding="utf-8")
    curation = curation_file(d, *CURATION)
    (d / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_extract(d / "in.osm.pbf")
    locate.main([str(d / "in.osm.pbf"), "--names", str(d / "places.csv"),
                 "--out", str(d / "osm_objects.json")])
    inject_names.run(str(d / "in.osm.pbf"), str(d / "out.osm.pbf"),
                     str(d / "places.csv"), paths.DIALECTS,
                     str(d / "areas.geojson"), curation_csv=curation,
                     objects_json=str(d / "osm_objects.json"))
    objs = read_extract(d / "out.osm.pbf")
    return objs, {(t, i): (tags, extra) for t, i, tags, extra in objs}


def test_output_is_nodes_then_ways_then_relations(injected):
    objs, _ = injected
    types = [t for t, *_ in objs]
    assert types == sorted(types, key="nwr".index)


@pytest.mark.parametrize("t", "nwr")
def test_output_ids_ascend_within_each_type(injected, t):
    objs, _ = injected
    ids = [i for tt, i, *_ in objs if tt == t]
    assert ids == sorted(ids) and len(ids) == len(set(ids))


def test_every_input_object_is_still_there(injected):
    _, by_key = injected
    for key in [("n", NORDSTRAND), ("n", HOLM), ("n", UNTOUCHED_NODE), ("n", TAMMENSIEL),
                ("w", NORDWARFT), ("w", HALLIG_RING), ("w", UNTOUCHED_WAY),
                ("r", KREIS), ("r", HAMBURGER_HALLIG)]:
        assert key in by_key


def test_objects_nobody_mentions_pass_unchanged(injected):
    _, by_key = injected
    assert by_key[("n", UNTOUCHED_NODE)] == ({"place": "village", "name": "Bredstedt"},
                                             pytest.approx((8.9, 54.6)))
    assert by_key[("w", UNTOUCHED_WAY)] == ({"highway": "track"}, [NORDSTRAND, HOLM])


def test_matched_node_gets_its_names_and_keeps_its_tags(injected):
    _, by_key = injected
    tags, _ = by_key[("n", HOLM)]
    # outside every dialect area: no frasch:dialect, no frasch:local
    assert tags == {"place": "village", "name": "Holm", "wikidata": "Q559369",
                    "name:frr-x-mooring": "Hulm", "frasch:kind": "settlement",
                    "frasch:ref": "hulm"}


def test_matched_way_gets_the_dialect_of_its_area(injected):
    _, by_key = injected
    tags, _ = by_key[("w", NORDWARFT)]
    assert tags == {"name": "Nordwarft", "landuse": "residential",
                    "name:frr-x-mooring": "Nordwärw",
                    "name:frr-x-nordgoes": "Noordweerw",
                    "frasch:kind": "warft", "frasch:dialect": "frr-x-nordgoes",
                    "frasch:local": "Noordweerw", "frasch:ref": "nordwarw"}


def test_matched_relation_gets_the_smallest_area_and_its_curation(injected):
    _, by_key = injected
    tags, _ = by_key[("r", HAMBURGER_HALLIG)]
    assert tags == {"type": "boundary", "boundary": "administrative",
                    "admin_level": "10", "name": "Hamburger Hallig",
                    "name:frr-x-mooring": "Hamborjer Håli", "frasch:kind": "hallig",
                    "frasch:dialect": "frr-x-hallig",
                    "frasch:ref": "hamborjer-hali",
                    "place": "island", "frasch:minzoom": "12"}


def test_a_district_gets_no_dialect(injected):
    _, by_key = injected
    tags, _ = by_key[("r", KREIS)]
    assert "frasch:dialect" not in tags and "frasch:local" not in tags
    assert tags["frasch:ref"] == "kris"


def test_an_object_nobody_located_stops_the_build(tmp_path):
    (tmp_path / "places.csv").write_text(places_csv([PLACES[0]]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    (tmp_path / "osm_objects.json").write_text(
        locate.objects_json(locate.Objects({}, {"extracts": []})), encoding="utf-8")
    write_extract(tmp_path / "in.osm.pbf")
    with pytest.raises(PipelineError, match=f"node/{HOLM}"):
        inject_names.run(str(tmp_path / "in.osm.pbf"), str(tmp_path / "out.osm.pbf"),
                         str(tmp_path / "places.csv"), paths.DIALECTS,
                         str(tmp_path / "areas.geojson"),
                         objects_json=str(tmp_path / "osm_objects.json"))
    assert not (tmp_path / "out.osm.pbf").exists()


def test_a_relations_member_way_is_left_alone(injected):
    _, by_key = injected
    assert by_key[("w", HALLIG_RING)][0] == {"natural": "coastline"}


def test_curation_applies_to_objects_the_name_list_does_not_know(injected):
    _, by_key = injected
    assert by_key[("n", TAMMENSIEL)][0] == {"place": "hamlet", "name": "Tammensiel",
                                            "frasch:minzoom": "10"}


def test_curation_tags_win_over_the_original_tags(injected):
    # the village node keeps place=village; only the square becomes an island
    _, by_key = injected
    assert by_key[("n", NORDSTRAND)][0] == {
        "place": "village", "name": "Nordstrand",
        "name:frr-x-mooring": "e Strönj", "frasch:ref": "relation/1420555",
        "frasch:minzoom": "12"}


def new_objects(by_key, t, above):
    return sorted((i, v) for (tt, i), v in by_key.items() if tt == t and i > above)


def test_local_reference_becomes_the_first_new_node(injected):
    _, by_key = injected
    (nid, (tags, loc)), *_ = new_objects(by_key, "n", MAX_NODE)
    assert nid == MAX_NODE + 1
    assert loc == pytest.approx((8.34019, 54.65097))
    assert tags == {"place": "hamlet", "name": "Westerheide",
                    "name:frr-x-oomrang": "Waasterhias", "frasch:kind": "settlement",
                    "frasch:dialect": "frr-x-oomrang", "frasch:local": "Waasterhias",
                    "frasch:ref": "waasterhias"}


def test_synthetic_square_is_one_new_closed_way(injected):
    _, by_key = injected
    ((wid, (_, refs)),) = new_objects(by_key, "w", MAX_WAY)
    assert wid == MAX_WAY + 1
    corners = [MAX_NODE + 2, MAX_NODE + 3, MAX_NODE + 4, MAX_NODE + 5]
    assert refs == corners + corners[:1]


def test_synthetic_square_nodes_are_written_as_untagged_nodes(injected):
    _, by_key = injected
    corners = new_objects(by_key, "n", MAX_NODE + 1)
    assert [nid for nid, _ in corners] == [MAX_NODE + 2, MAX_NODE + 3,
                                          MAX_NODE + 4, MAX_NODE + 5]
    assert all(tags == {} for _, (tags, _) in corners)


def test_synthetic_square_is_fifty_km2_around_the_village_node(injected):
    _, by_key = injected
    corners = [loc for _, (_, loc) in new_objects(by_key, "n", MAX_NODE + 1)]
    lon = sum(x for x, _ in corners) / 4
    lat = sum(y for _, y in corners) / 4
    assert (lon, lat) == pytest.approx((8.865286, 54.487378), abs=1e-6)
    side_ns = (max(y for _, y in corners) - min(y for _, y in corners)) * 111.32
    side_ew = ((max(x for x, _ in corners) - min(x for x, _ in corners))
               * 111.32 * math.cos(math.radians(54.487378)))
    assert side_ns == pytest.approx(math.sqrt(50), rel=1e-4)
    assert side_ew == pytest.approx(math.sqrt(50), rel=1e-4)


def test_synthetic_square_carries_the_nodes_names_and_its_own_tags(injected):
    # names and ref from the (curated) node; place/kind/maxzoom from the
    # polygon row -- but not the node's own minzoom, which holds it to z12
    _, by_key = injected
    ((_, (tags, _)),) = new_objects(by_key, "w", MAX_WAY)
    assert tags == {"name": "Nordstrand", "name:frr-x-mooring": "e Strönj",
                    "frasch:ref": "relation/1420555", "place": "island",
                    "frasch:kind": "island", "frasch:maxzoom": "11"}
