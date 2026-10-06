"""inject_names.py: an absent curation file, the tags an object gets, and a
whole `run()` over a tiny extract written here with pyosmium.

The extract mirrors real places (ids and positions from the
Schleswig-Holstein extract; ring nodes made up): the village Holm, the
Nordwarft way on Ockholm, the Hamburger Hallig relation, the Nordstrand
village node that carries the synthetic island square, Tammensiel (curated,
not in the name list), Westerheide on Amrum, a place OSM does not have, and
the Kirchwarft, which no row claims but OSM names in Frisian (#81; moved into
the Mooring box of AREAS)."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import osmium
import pytest

from frasch.errors import PipelineError
from frasch import inject_names
from frasch import locate
from frasch import placelist
from frasch.__main__ import main
from frasch.geo import LonLat
from frasch.inject_names import Use
from frasch.objects import Objects, objects_json
from frasch.provenance import Stamp
from frasch.registry import Registry
from conftest import REGISTRY, curation_file, flat_workspace, path_options
from osm_fixture import Nodes, write_extract as write_osm


# ------------------------------------------------------------- square_around ---
def test_square_at_the_equator() -> None:
    # 4 km² -> 1 km from the centre to each side; 1 km = 1/111.32 degree
    d = 1 / 111.32
    corners = inject_names.square_around(0.0, 0.0, 4.0)
    assert corners == pytest.approx([(-d, -d), (d, -d), (d, d), (-d, d)])


def test_square_at_sixty_degrees_is_twice_as_wide_in_longitude() -> None:
    # cos 60° = 1/2: a kilometre spans twice the degrees of longitude
    d = 1 / 111.32
    (w, s), (e, _), (_, n), _ = inject_names.square_around(8.0, 60.0, 4.0)
    assert (w, e) == pytest.approx((8.0 - 2 * d, 8.0 + 2 * d))
    assert (s, n) == pytest.approx((60.0 - d, 60.0 + d))


def test_square_is_centred_on_the_node() -> None:
    # Planetiler labels a polygon at its interior point: that must be the node
    corners = inject_names.square_around(8.865286, 54.487378, 50.0)
    assert sum(x for x, _ in corners) / 4 == pytest.approx(8.865286)
    assert sum(y for _, y in corners) / 4 == pytest.approx(54.487378)


# ----------------------------------------------------------------- name_tags ---
@pytest.fixture(scope="module")
def reg() -> Registry:
    return REGISTRY


def place(line: int = 2, **cells: str) -> placelist.PlaceRow:
    return placelist.PlaceRow({c: "" for c in placelist.columns(REGISTRY)} | cells, line)


BRODERSWARFT = place(
    id="brouderswarw",
    kind="warft",
    mooring="Brouderswärw",
    local="Brouersweerw (Foortuftinge)",
    de="Broderswarft",
    osm="node/1594721085",
)


def test_name_tags_of_a_row_with_a_local_variety(reg: Registry) -> None:
    assert inject_names.name_tags([BRODERSWARFT], "frr-x-mooring", reg) == {
        "name:frr-x-mooring": "Brouderswärw",
        "name:de": "Broderswarft",
        "frasch:kind": "warft",
        "frasch:dialect": "frr-x-mooring",
        "frasch:local": "Brouersweerw",
        "frasch:variety": "Foortuftinge",
        "frasch:ref": "brouderswarw",
    }


def test_name_tags_fill_the_areas_dialect_from_local(reg: Registry) -> None:
    tags = inject_names.name_tags([BRODERSWARFT], "frr-x-nordgoes", reg)
    assert tags["name:frr-x-nordgoes"] == "Brouersweerw"


def test_name_tags_outside_any_area_have_no_dialect(reg: Registry) -> None:
    hanswarft = place(
        id="hanswarw",
        kind="warft",
        mooring="Hanswärw",
        hallig="Hansweerf",
        de="Hanswarft",
        osm="node/3410324993",
    )
    assert inject_names.name_tags([hanswarft], None, reg) == {
        "name:frr-x-mooring": "Hanswärw",
        "name:frr-x-hallig": "Hansweerf",
        "name:de": "Hanswarft",
        "frasch:kind": "warft",
        "frasch:ref": "hanswarw",
    }


def test_name_tags_first_row_wins_per_tag(reg: Registry) -> None:
    # two rows claim one object: the first in file order keeps its names,
    # the second only fills what the first leaves empty
    first = place(2, id="hulm", kind="settlement", mooring="Hulm", de="Holm", osm="node/240102263")
    second = place(
        9,
        id="hulm-gutskuuch",
        kind="koog",
        mooring="Hulm Gutskuuch",
        wieding="Hoolm",
        de="Holmer Gotteskoog",
        osm="node/240102263",
    )
    tags = inject_names.name_tags([first, second], None, reg)
    assert tags["name:frr-x-mooring"] == "Hulm"
    assert tags["name:de"] == "Holm"
    assert tags["name:frr-x-wieding"] == "Hoolm"
    assert tags["frasch:kind"] == "settlement"
    assert tags["frasch:ref"] == "hulm"


def test_name_tags_carry_the_lists_german_name(reg: Registry) -> None:
    # the map's name:de step must say what the card's says, which is the
    # list's `de` (#61) -- its first variant, as names.json's name_de
    listlai = place(
        id="listlai", kind="water", solring="Listlai", de="Lister Ley; Ley", osm="way/1273915431"
    )
    assert inject_names.name_tags([listlai], None, reg)["name:de"] == "Lister Ley"


def test_name_tags_refer_to_the_rows_id(reg: Registry) -> None:
    # not to the object: the search index names the place by the row (#23)
    denmark = place(
        id="daanemark", kind="country", mooring="Däänemark", de="Dänemark", wikidata="Q35"
    )
    assert inject_names.name_tags([denmark], None, reg)["frasch:ref"] == "daanemark"


# ------------------------------------------------------------- load_curation ---
# (the file's rules are frasch.curationlist's, see names/tests/test_curationlist.py)
def test_a_second_row_with_the_same_qid_is_reported(tmp_path: Path, reg: Registry) -> None:
    path = tmp_path / "places.csv"
    path.write_text(
        places_csv(
            [
                {"id": "daanemark", "kind": "country", "mooring": "Däänemark", "wikidata": "Q35"},
                {"id": "daanemoark", "kind": "country", "mooring": "Däänemoark", "wikidata": "Q35"},
            ]
        ),
        encoding="utf-8",
    )
    names = inject_names.load_names(str(path), reg)
    assert [r["id"] for r in names.by_qid["Q35"]] == ["daanemark"]
    assert names.duplicate_qids == [("Q35", 2, 3)]


def test_missing_curation_file_is_nothing_curated(tmp_path: Path) -> None:
    assert inject_names.load_curation(str(tmp_path / "absent.csv")) == ({}, {}, {})


def test_missing_curation_file_named_explicitly_stops(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="not found"):
        inject_names.load_curation(str(tmp_path / "absent.csv"), required=True)


# ------------------------------------------------------------ a whole run() ---
HOLM = 240102263
NORDSTRAND = 85929111
TAMMENSIEL = 355956234
UNTOUCHED_NODE = 240000001
JENSWARFT = 188786563
NORDWARFT = 1347936331
HALLIG_RING = 500000001
UNTOUCHED_WAY = 600000001
HAMBURGER_HALLIG = 5615880
KREIS = 27019
KIRCHWARFT = 14204794496
PINNEBERG = 240033277

# closed rings: the Nordwarft on Ockholm, the Jenswarft (moved into the
# Mooring box of AREAS, like the Kirchwarft), the Hamburger Hallig's outline
NORDWARFT_NODES = {
    9000000001: (8.826, 54.668),
    9000000002: (8.830, 54.668),
    9000000003: (8.830, 54.671),
    9000000004: (8.826, 54.671),
}
JENSWARFT_NODES = {
    9000000011: (8.900, 54.570),
    9000000012: (8.904, 54.570),
    9000000013: (8.904, 54.572),
    9000000014: (8.900, 54.572),
}
HALLIG_NODES = {
    9100000001: (8.825, 54.585),
    9100000002: (8.850, 54.585),
    9100000003: (8.850, 54.600),
    9100000004: (8.825, 54.600),
}
MAX_NODE = KIRCHWARFT
MAX_WAY = NORDWARFT

PLACES = [
    dict(
        id="hulm",
        kind="settlement",
        mooring="Hulm",
        de="Holm",
        osm=f"node/{HOLM}",
        wikidata="Q559369",
        status="ok",
    ),
    dict(
        id="nordwarw",
        kind="warft",
        mooring="Nordwärw",
        nordgoes="Noordweerw",
        de="Nordwarft",
        hint="Ockholm",
        osm=f"way/{NORDWARFT}",
        status="ok",
    ),
    dict(
        id="hamborjer-hali",
        kind="hallig",
        mooring="Hamborjer Håli",
        de="Hamburger Hallig",
        osm=f"relation/{HAMBURGER_HALLIG}",
        status="ok",
    ),
    # the Kreis relation runs along the Hallig's outline here: a district
    # around a Hallig, so its inside point lies in the Hallig's area; no
    # German name in the list, OSM has one
    dict(
        id="kris",
        kind="landscape",
        mooring="Kris Nordfraschlönj",
        nordgoes="Noordfräischloun Krais",
        osm=f"relation/{KREIS}",
        status="ok",
    ),
    dict(
        id="waasterhias",
        kind="settlement",
        oomrang="Waasterhias",
        de="Westerheide",
        osm="local/westerheide-amrum",
        status="ok",
    ),
]

CURATION = [
    {
        "osm": f"node/{NORDSTRAND}",
        "name": "Nordstrand (synthetic island polygon)",
        "set_tags": "place=island;frasch:kind=island",
        "maxzoom": "11",
        "polygon_km2": "50",
    },
    {
        "osm": f"node/{NORDSTRAND}",
        "name": "Nordstrand (village node)",
        "set_tags": "name:frr-x-mooring=e Strönj;frasch:ref=relation/1420555",
        "minzoom": "12",
    },
    {"osm": f"node/{TAMMENSIEL}", "name": "Tammensiel", "minzoom": "10"},
    {
        "osm": f"relation/{HAMBURGER_HALLIG}",
        "name": "Hamburger Hallig",
        "set_tags": "place=island",
        "minzoom": "12",
    },
    {
        "osm": "local/westerheide-amrum",
        "name": "Westerheide (Amrum)",
        "lat": "54.65097",
        "lon": "8.34019",
    },
]


def box(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


# Amrum; Ockholm (Nordergoesharde); Reußenköge (Mooring) with the Hamburger
# Hallig (Halligfriesisch) inside it -- the smaller area must win
AREAS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"dialect": tag},
            "geometry": {"type": "Polygon", "coordinates": box(*bounds)},
        }
        for tag, bounds in [
            ("frr-x-oomrang", (8.30, 54.62, 8.40, 54.70)),
            ("frr-x-nordgoes", (8.78, 54.64, 8.90, 54.70)),
            ("frr-x-mooring", (8.80, 54.55, 8.95, 54.63)),
            ("frr-x-hallig", (8.82, 54.58, 8.86, 54.605)),
        ]
    ],
}


def write_extract(path: Path) -> None:
    Node, Way, Relation = (
        osmium.osm.mutable.Node,
        osmium.osm.mutable.Way,
        osmium.osm.mutable.Relation,
    )
    nodes = {
        NORDSTRAND: ((8.865286, 54.487378), {"place": "village", "name": "Nordstrand"}),
        HOLM: ((8.866668, 54.833305), {"place": "village", "name": "Holm", "wikidata": "Q559369"}),
        UNTOUCHED_NODE: ((8.9, 54.6), {"place": "village", "name": "Bredstedt"}),
        TAMMENSIEL: ((8.7033, 54.7433), {"place": "hamlet", "name": "Tammensiel"}),
        KIRCHWARFT: (
            (8.88, 54.56),
            {"place": "hamlet", "name": "Kirchwarft", "name:frr": "Schörkeweerw"},
        ),
        PINNEBERG: ((9.80, 53.66), {"place": "town", "name": "Pinneberg", "name:frr": "Pinebärj"}),
    }
    nodes.update({i: (loc, {}) for i, loc in NORDWARFT_NODES.items()})
    nodes.update({i: (loc, {}) for i, loc in JENSWARFT_NODES.items()})
    nodes.update({i: (loc, {}) for i, loc in HALLIG_NODES.items()})
    w = osmium.SimpleWriter(str(path))
    try:
        for nid in sorted(nodes):
            loc, tags = nodes[nid]
            w.add_node(Node(id=nid, version=1, visible=True, location=loc, tags=tags))
        # ways in ascending id order, like any extract
        ring = list(JENSWARFT_NODES)
        w.add_way(
            Way(
                id=JENSWARFT,
                version=1,
                visible=True,
                nodes=ring + ring[:1],
                tags={"name": "Jenswarft", "name:frr": "Jenswäärw", "landuse": "residential"},
            )
        )
        ring = list(HALLIG_NODES)
        w.add_way(
            Way(
                id=HALLIG_RING,
                version=1,
                visible=True,
                nodes=ring + ring[:1],
                tags={"natural": "coastline"},
            )
        )
        w.add_way(
            Way(
                id=UNTOUCHED_WAY,
                version=1,
                visible=True,
                nodes=[NORDSTRAND, HOLM],
                tags={"highway": "track"},
            )
        )
        ring = list(NORDWARFT_NODES)
        w.add_way(
            Way(
                id=NORDWARFT,
                version=1,
                visible=True,
                nodes=ring + ring[:1],
                tags={"name": "Nordwarft", "name:frr": "Nöördweerew", "landuse": "residential"},
            )
        )
        w.add_relation(
            Relation(
                id=KREIS,
                version=1,
                visible=True,
                members=[("w", HALLIG_RING, "outer")],
                tags={
                    "type": "boundary",
                    "boundary": "administrative",
                    "admin_level": "6",
                    "name": "Kreis Nordfriesland",
                    "name:de": "Nordfriesland",
                    "name:frr": "Nuurdfresklun",
                },
            )
        )
        w.add_relation(
            Relation(
                id=HAMBURGER_HALLIG,
                version=1,
                visible=True,
                members=[("w", HALLIG_RING, "outer")],
                tags={
                    "type": "boundary",
                    "boundary": "administrative",
                    "admin_level": "10",
                    "name": "Hamburger Hallig",
                    "name:frr": "Hamborjer Hali",
                },
            )
        )
    finally:
        w.close()


# a node's (lon, lat), a way's node ids, nothing for a relation
Extra = LonLat | list[int] | None
# (type letter, id, tags, extra)
ExtractObject = tuple[str, int, dict[str, str], Extra]
# the objects in file order, and by (type letter, id)
Injected = tuple[list[ExtractObject], dict[tuple[str, int], tuple[dict[str, str], Extra]]]


def read_extract(path: Path) -> list[ExtractObject]:
    """-> [(type letter, id, tags, extra)] in file order; `extra` is a
    node's (lon, lat) or a way's node ids."""
    out: list[ExtractObject] = []
    for o in osmium.FileProcessor(str(path)):
        t = o.type_str()
        extra: Extra = (
            (o.location.lon, o.location.lat)
            if isinstance(o, osmium.osm.Node)
            else [n.ref for n in o.nodes]
            if isinstance(o, osmium.osm.Way)
            else None
        )
        out.append((t, o.id, dict(o.tags), extra))
    return out


def places_csv(rows: Iterable[Mapping[str, str]]) -> str:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=placelist.columns(REGISTRY), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in placelist.columns(REGISTRY)})
    return buf.getvalue()


def inject(
    d: Path, *, areas: Use = Use.OFF, curation: Use = Use.OFF, dry_run: bool = False
) -> None:
    """Inject the name files of `d` into its in.osm.pbf, as out.osm.pbf."""
    inject_names.run(
        flat_workspace(d),
        REGISTRY,
        str(d / "in.osm.pbf"),
        str(d / "out.osm.pbf"),
        dry_run=dry_run,
        areas=areas,
        curation=curation,
    )


def locate_objects(d: Path) -> None:
    """Write the objects file of `d` from its in.osm.pbf."""
    locate.run(flat_workspace(d), REGISTRY, [d / "in.osm.pbf"])


def normalized(report: str, directory: Path) -> str:
    """`report` with the run's directory as `<dir>` and its time as `0s`."""
    return re.sub(r" in \d+s\n", " in 0s\n", report.replace(str(directory), "<dir>"))


@pytest.fixture(scope="module")
def injected_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """-> (the run's directory, the report it printed)"""
    d = tmp_path_factory.mktemp("inject")
    (d / "places.csv").write_text(places_csv(PLACES), encoding="utf-8")
    curation_file(d, *CURATION)
    (d / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_extract(d / "in.osm.pbf")
    locate_objects(d)
    report = io.StringIO()
    with contextlib.redirect_stdout(report):
        inject(d, areas=Use.IF_PRESENT, curation=Use.IF_PRESENT)
    return d, normalized(report.getvalue(), d)


@pytest.fixture(scope="module")
def injected(injected_run: tuple[Path, str]) -> Injected:
    d, _ = injected_run
    objs = read_extract(d / "out.osm.pbf")
    return objs, {(t, i): (tags, extra) for t, i, tags, extra in objs}


def test_report_of_a_run(injected_run: tuple[Path, str]) -> None:
    _, report = injected_run
    lines = report.splitlines()
    assert lines[1].startswith("dialects  : <dir>/dialects.csv -> ")
    assert lines[:1] + lines[2:] == [
        "name list : <dir>/places.csv",
        "usable    : 5 rows -> 4 OSM ids + 1 wikidata QIDs + 1 local reference(s)",
        "areas     : <dir>/areas.geojson -> 4 polygon(s): frr-x-hallig (1), frr-x-mooring (1), "
        "frr-x-nordgoes (1), frr-x-oomrang (1)",
        "curation  : <dir>/curation.csv -> 3 OSM ids (3 with frasch:minzoom, 0 with frasch:maxzoom)",
        "synthetic : 1 polygon(s) to add around nodes",
        "local     : 1 local reference(s) positioned in <dir>/curation.csv",
        "objects   : <dir>/osm_objects.json -> 4 located object(s)",
        "name:frr  : 4 object(s) in a dialect area have one in OSM",
        "",
        "scanned 24 objects in 0s",
        "tagged  5 objects: 2 nodes, 1 ways, 2 relations "
        "(of these 0 matched by wikidata: 1 of 1 QIDs present)",
        "names written per dialect:",
        "  name:frr-x-mooring       4  Mooring",
        "  name:frr-x-nordgoes      2  Nordergoesharder",
        "  name:frr-x-oomrang       1  Öömrang",
        "  frasch:local             3  local form (1 of them OSM's name:frr)",
        "  frasch:local             2  OSM's name:frr on objects no row claims",
        "objects per dialect area:",
        "  frasch:dialect=frr-x-oomrang       1",
        "  frasch:dialect=frr-x-nordgoes      1",
        "  frasch:dialect=frr-x-hallig        1",
        "",
        "added 1 node(s) for places that are not in OSM:",
        f"  node/{MAX_NODE + 1}  local/westerheide-amrum Waasterhias (Westerheide) "
        "at 54.65097, 8.34019: frasch:dialect=frr-x-oomrang, frasch:kind=settlement, "
        "frasch:local=Waasterhias, frasch:ref=waasterhias, place=hamlet",
        "",
        "curated 3 objects: 2 nodes, 0 ways, 1 relations",
        f"  n/{NORDSTRAND}  Nordstrand (village node): frasch:minzoom=12, "
        "frasch:ref=relation/1420555, name:frr-x-mooring=e Strönj",
        f"  n/{TAMMENSIEL}  Tammensiel: frasch:minzoom=10",
        f"  r/{HAMBURGER_HALLIG}  Hamburger Hallig: frasch:minzoom=12, place=island",
        "",
        "added 1 synthetic polygon(s):",
        f"  way/{MAX_WAY + 1} (nodes {MAX_NODE + 2}..{MAX_NODE + 5})  "
        "Nordstrand (synthetic island polygon): 50 km²",
        "",
        "wrote <dir>/out.osm.pbf (0.0 MB)",
    ]


def test_output_is_nodes_then_ways_then_relations(injected: Injected) -> None:
    objs, _ = injected
    types = [t for t, *_ in objs]
    assert types == sorted(types, key="nwr".index)


@pytest.mark.parametrize("t", "nwr")
def test_output_ids_ascend_within_each_type(injected: Injected, t: str) -> None:
    objs, _ = injected
    ids = [i for tt, i, *_ in objs if tt == t]
    assert ids == sorted(ids) and len(ids) == len(set(ids))


def test_every_input_object_is_still_there(injected: Injected) -> None:
    _, by_key = injected
    for key in [
        ("n", NORDSTRAND),
        ("n", HOLM),
        ("n", UNTOUCHED_NODE),
        ("n", TAMMENSIEL),
        ("w", NORDWARFT),
        ("w", HALLIG_RING),
        ("w", UNTOUCHED_WAY),
        ("r", KREIS),
        ("r", HAMBURGER_HALLIG),
    ]:
        assert key in by_key


def test_objects_nobody_mentions_pass_unchanged(injected: Injected) -> None:
    _, by_key = injected
    tags, loc = by_key[("n", UNTOUCHED_NODE)]
    assert tags == {"place": "village", "name": "Bredstedt"}
    assert loc == pytest.approx((8.9, 54.6))
    assert by_key[("w", UNTOUCHED_WAY)] == ({"highway": "track"}, [NORDSTRAND, HOLM])


def test_matched_node_gets_its_names_and_keeps_its_tags(injected: Injected) -> None:
    _, by_key = injected
    tags, _ = by_key[("n", HOLM)]
    # outside every dialect area: no frasch:dialect, no frasch:local
    assert tags == {
        "place": "village",
        "name": "Holm",
        "wikidata": "Q559369",
        "name:frr-x-mooring": "Hulm",
        "name:de": "Holm",
        "frasch:kind": "settlement",
        "frasch:ref": "hulm",
    }


def test_matched_way_gets_the_dialect_of_its_area(injected: Injected) -> None:
    _, by_key = injected
    tags, _ = by_key[("w", NORDWARFT)]
    assert tags == {
        "name": "Nordwarft",
        "name:frr": "Nöördweerew",
        "landuse": "residential",
        "name:frr-x-mooring": "Nordwärw",
        "name:frr-x-nordgoes": "Noordweerw",
        "name:de": "Nordwarft",
        "frasch:kind": "warft",
        "frasch:dialect": "frr-x-nordgoes",
        "frasch:local": "Noordweerw",
        "frasch:ref": "nordwarw",
    }


def test_matched_relation_gets_the_smallest_area_and_its_curation(injected: Injected) -> None:
    _, by_key = injected
    tags, _ = by_key[("r", HAMBURGER_HALLIG)]
    assert tags == {
        "type": "boundary",
        "boundary": "administrative",
        "admin_level": "10",
        "name": "Hamburger Hallig",
        "name:frr": "Hamborjer Hali",
        "name:frr-x-mooring": "Hamborjer Håli",
        "name:de": "Hamburger Hallig",
        "frasch:kind": "hallig",
        "frasch:dialect": "frr-x-hallig",
        "frasch:local": "Hamborjer Hali",
        "frasch:ref": "hamborjer-hali",
        "place": "island",
        "frasch:minzoom": "12",
    }


def test_a_district_gets_no_dialect(injected: Injected) -> None:
    _, by_key = injected
    tags, _ = by_key[("r", KREIS)]
    assert "frasch:dialect" not in tags and "frasch:local" not in tags
    assert tags["frasch:ref"] == "kris"


def test_osms_german_name_stays_where_the_list_has_none(injected: Injected) -> None:
    _, by_key = injected
    tags, _ = by_key[("r", KREIS)]
    assert tags["name:de"] == "Nordfriesland"


def test_an_object_nobody_located_stops_the_build(tmp_path: Path) -> None:
    (tmp_path / "places.csv").write_text(places_csv([PLACES[0]]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    (tmp_path / "osm_objects.json").write_text(
        objects_json(Objects({}, Stamp({}, []))), encoding="utf-8"
    )
    write_extract(tmp_path / "in.osm.pbf")
    with pytest.raises(PipelineError, match=f"node/{HOLM}"):
        inject(tmp_path, areas=Use.IF_PRESENT)
    assert not (tmp_path / "out.osm.pbf").exists()


def test_a_relations_member_way_is_left_alone(injected: Injected) -> None:
    _, by_key = injected
    assert by_key[("w", HALLIG_RING)][0] == {"natural": "coastline"}


def test_curation_applies_to_objects_the_name_list_does_not_know(injected: Injected) -> None:
    _, by_key = injected
    assert by_key[("n", TAMMENSIEL)][0] == {
        "place": "hamlet",
        "name": "Tammensiel",
        "frasch:minzoom": "10",
    }


def test_curation_tags_win_over_the_original_tags(injected: Injected) -> None:
    # the village node keeps place=village; only the square becomes an island
    _, by_key = injected
    assert by_key[("n", NORDSTRAND)][0] == {
        "place": "village",
        "name": "Nordstrand",
        "name:frr-x-mooring": "e Strönj",
        "frasch:ref": "relation/1420555",
        "frasch:minzoom": "12",
    }


# ------------------------------------------- OSM's own Frisian name (#81) ---
def test_an_object_no_row_claims_gets_osms_frisian_name_as_its_local_one(
    injected: Injected,
) -> None:
    _, by_key = injected
    assert by_key[("n", KIRCHWARFT)][0] == {
        "place": "hamlet",
        "name": "Kirchwarft",
        "name:frr": "Schörkeweerw",
        "frasch:local": "Schörkeweerw",
    }


def test_outside_every_dialect_area_osms_frisian_name_is_no_local_name(
    injected: Injected,
) -> None:
    # a Frisian exonym: Frisian was never spoken in Pinneberg
    _, by_key = injected
    assert by_key[("n", PINNEBERG)][0] == {
        "place": "town",
        "name": "Pinneberg",
        "name:frr": "Pinebärj",
    }


def test_a_way_no_row_claims_is_asked_where_its_polygon_lies(injected: Injected) -> None:
    _, by_key = injected
    assert by_key[("w", JENSWARFT)][0]["frasch:local"] == "Jenswäärw"


def test_the_lists_local_name_wins_over_osms_frisian_one(injected: Injected) -> None:
    _, by_key = injected
    assert by_key[("w", NORDWARFT)][0]["frasch:local"] == "Noordweerw"


def test_a_row_without_a_local_name_gets_osms_frisian_one(injected: Injected) -> None:
    # the row has a Mooring name only, the Hallig lies in the Halligfriesisch area
    _, by_key = injected
    assert by_key[("r", HAMBURGER_HALLIG)][0]["frasch:local"] == "Hamborjer Hali"


def new_objects(
    by_key: Mapping[tuple[str, int], tuple[dict[str, str], Extra]], t: str, above: int
) -> list[tuple[int, tuple[dict[str, str], Extra]]]:
    return sorted((i, v) for (tt, i), v in by_key.items() if tt == t and i > above)


def test_local_reference_becomes_the_first_new_node(injected: Injected) -> None:
    _, by_key = injected
    (nid, (tags, loc)), *_ = new_objects(by_key, "n", MAX_NODE)
    assert nid == MAX_NODE + 1
    assert loc == pytest.approx((8.34019, 54.65097))
    assert tags == {
        "place": "hamlet",
        "name": "Westerheide",
        "name:frr-x-oomrang": "Waasterhias",
        "name:de": "Westerheide",
        "frasch:kind": "settlement",
        "frasch:dialect": "frr-x-oomrang",
        "frasch:local": "Waasterhias",
        "frasch:ref": "waasterhias",
    }


def test_synthetic_square_is_one_new_closed_way(injected: Injected) -> None:
    _, by_key = injected
    ((wid, (_, refs)),) = new_objects(by_key, "w", MAX_WAY)
    assert wid == MAX_WAY + 1
    corners = [MAX_NODE + 2, MAX_NODE + 3, MAX_NODE + 4, MAX_NODE + 5]
    assert refs == corners + corners[:1]


def test_synthetic_square_nodes_are_written_as_untagged_nodes(injected: Injected) -> None:
    _, by_key = injected
    corners = new_objects(by_key, "n", MAX_NODE + 1)
    assert [nid for nid, _ in corners] == [MAX_NODE + 2, MAX_NODE + 3, MAX_NODE + 4, MAX_NODE + 5]
    assert all(tags == {} for _, (tags, _) in corners)


def test_synthetic_square_is_fifty_km2_around_the_village_node(injected: Injected) -> None:
    _, by_key = injected
    corners = [
        loc for _, (_, loc) in new_objects(by_key, "n", MAX_NODE + 1) if isinstance(loc, tuple)
    ]
    lon = sum(x for x, _ in corners) / 4
    lat = sum(y for _, y in corners) / 4
    assert (lon, lat) == pytest.approx((8.865286, 54.487378), abs=1e-6)
    side_ns = (max(y for _, y in corners) - min(y for _, y in corners)) * 111.32
    side_ew = (
        (max(x for x, _ in corners) - min(x for x, _ in corners))
        * 111.32
        * math.cos(math.radians(54.487378))
    )
    assert side_ns == pytest.approx(math.sqrt(50), rel=1e-4)
    assert side_ew == pytest.approx(math.sqrt(50), rel=1e-4)


def test_synthetic_square_carries_the_nodes_names_and_its_own_tags(injected: Injected) -> None:
    # names and ref from the (curated) node; place/kind/maxzoom from the
    # polygon row -- but not the node's own minzoom, which holds it to z12
    _, by_key = injected
    ((_, (tags, _)),) = new_objects(by_key, "w", MAX_WAY)
    assert tags == {
        "name": "Nordstrand",
        "name:frr-x-mooring": "e Strönj",
        "frasch:ref": "relation/1420555",
        "place": "island",
        "frasch:kind": "island",
        "frasch:maxzoom": "11",
    }


# ------------------------------------------------------------ the report ---
# a dry run over a second extract, for what the report says about rows and
# curation rows that do not fit: two rows on Holm, a QID-only row (the North
# Sea), the Arlau with one same-named and one renamed member way, ids and
# local references nobody can place, a shop that carries Holm's QID
REPORT_PLACES = [
    dict(
        id="hulm",
        kind="settlement",
        mooring="Hulm",
        de="Holm",
        osm="node/1",
        wikidata="Q559369",
        status="ok",
    ),
    dict(
        id="hoolm",
        kind="settlement",
        mooring="Hoolm",
        de="Holm",
        osm="node/1",
        wikidata="Q559369",
        status="ok",
    ),
    dict(id="nordsiie", kind="water", mooring="Nordsiie", de="Nordsee", wikidata="Q1693"),
    dict(id="arlau", kind="water", mooring="Arlau", de="Arlau", osm="relation/20"),
    dict(id="braist", kind="settlement", mooring="Bräist", de="Bredstedt", osm="node/99"),
    dict(
        id="sofiinkuuch",
        kind="koog",
        mooring="Sofiinkuuch",
        de="Sophien-Koog",
        osm="local/sophien-koog",
    ),
]

REPORT_CURATION = [
    {"osm": "node/1", "name": "Holm", "minzoom": "11"},
    {"osm": "node/98", "name": "Gone", "minzoom": "10"},
    {"osm": "node/97", "name": "Gone island", "set_tags": "place=island", "polygon_km2": "5"},
    {
        "osm": "local/sophien-koog",
        "name": "Sophien-Koog",
        "lat": "54.6",
        "lon": "8.9",
        "set_tags": "place=island",
        "polygon_km2": "2",
    },
    {"osm": "local/nowhere", "name": "Nowhere", "lat": "54.7", "lon": "8.8"},
]


def write_report_extract(path: Path) -> None:
    write_osm(
        path,
        nodes={
            1: ((8.9, 54.6), {"place": "village", "name": "Holm"}),
            2: ((7.5, 54.5), {"place": "sea", "name": "Nordsee", "wikidata": "Q1693"}),
            3: ((8.91, 54.61), {}),
            4: ((8.92, 54.61), {}),
            5: ((8.93, 54.61), {}),
            # a shop mis-tagged with Holm's QID
            6: ((8.9, 54.6), {"shop": "gift", "name": "Rosen-Huus", "wikidata": "Q559369"}),
        },
        ways={
            10: ([3, 4], {"waterway": "river", "name": "Arlau"}),
            11: ([4, 5], {"waterway": "river", "name": "Alte Arlau"}),
        },
        relations={
            20: (
                [("w", 10, "main_stream"), ("w", 11, "side_stream")],
                {"type": "waterway", "name": "Arlau"},
            )
        },
    )


def report_run(
    d: Path,
    places: Iterable[Mapping[str, str]],
    curation: Iterable[Mapping[str, str]],
    areas: Use = Use.OFF,
) -> None:
    """A dry run over the report extract, without dialect areas unless `areas` says so."""
    (d / "places.csv").write_text(places_csv(places), encoding="utf-8")
    write_report_extract(d / "in.osm.pbf")
    curation_file(d, *curation)
    inject(d, areas=areas, curation=Use.IF_PRESENT, dry_run=True)


def test_report_of_rows_and_curation_rows_that_do_not_fit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_run(tmp_path, REPORT_PLACES, REPORT_CURATION)
    lines = normalized(capsys.readouterr().out, tmp_path).splitlines()
    assert lines[1].startswith("dialects  : <dir>/dialects.csv -> ")
    assert lines[:1] + lines[2:] == [
        "name list : <dir>/places.csv",
        "usable    : 6 rows -> 3 OSM ids + 2 wikidata QIDs + 1 local reference(s)",
        "  ! node/1 claimed twice in `mooring`: keeping 'Hulm' (line 2), "
        "ignoring 'Hoolm' (places.csv line 3)",
        "  ! Q559369 claimed twice: keeping line 2, ignoring places.csv line 3",
        "areas     : off (no frasch:dialect; frasch:local only from the `local` column). "
        "Build it with `just areas`",
        "curation  : <dir>/curation.csv -> 2 OSM ids (2 with frasch:minzoom, 0 with frasch:maxzoom)",
        "synthetic : 1 polygon(s) to add around nodes",
        "local     : 2 local reference(s) positioned in <dir>/curation.csv",
        "  ! local/nowhere (Nowhere) is positioned in <dir>/curation.csv but no row of "
        "<dir>/places.csv uses it -- nothing added",
        "waterways : 2 member ways of matched waterway relations",
        "",
        "scanned 9 objects in 0s",
        "tagged  5 objects: 2 nodes, 2 ways, 1 relations (of these 1 matched by wikidata: "
        "2 of 2 QIDs present); 1 same-named member ways of waterway relations",
        "names written per dialect:",
        "  name:frr-x-mooring       5  Mooring",
        "  frasch:local             0  local form",
        "",
        "1 rows reference ids that are not in in.osm.pbf:",
        "  node/99  Bräist",
        "",
        "1 objects carry a QID of the list but are not place-like -- not tagged:",
        "  n/6  Rosen-Huus: Q559369 (Hulm)",
        "",
        "curated 1 objects: 1 nodes, 0 ways, 0 relations",
        "  n/1  Holm: frasch:minzoom=11",
        "",
        "1 curation rows reference ids that are not in in.osm.pbf:",
        "  n/98  Gone",
        "",
        "added 1 synthetic polygon(s):",
        "  way/12 (nodes 7..10)  Sophien-Koog: 2 km²",
        "  ! n/97 Gone island: node not in in.osm.pbf, no polygon added",
        "",
        "(dry run -- nothing written)",
    ]


def test_report_names_a_curation_file_without_osm_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # only the Sophien-Koog's label square
    report_run(tmp_path, REPORT_PLACES[5:], REPORT_CURATION[3:4])
    lines = normalized(capsys.readouterr().out, tmp_path).splitlines()
    assert (
        "curation  : <dir>/curation.csv -> 0 OSM ids (0 with frasch:minzoom, 0 with frasch:maxzoom)"
    ) in lines


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    report_run(tmp_path, REPORT_PLACES[:1], [])
    assert not (tmp_path / "out.osm.pbf").exists()


def test_a_local_reference_without_a_position_stops_the_build(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as exc:
        report_run(tmp_path, REPORT_PLACES, REPORT_CURATION[:3])
    assert normalized(str(exc.value), tmp_path) == (
        "1 local reference(s) in <dir>/places.csv have no row with lat/lon in "
        "<dir>/curation.csv:\n"
        "  local/sophien-koog  Sofiinkuuch (Sophien-Koog) (places.csv line 7)"
    )


def test_a_named_dialect_area_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as exc:
        report_run(tmp_path, REPORT_PLACES[:1], [], areas=Use.REQUIRED)
    assert normalized(str(exc.value), tmp_path) == (
        "dialect area file not found: <dir>/areas.geojson"
    )


def test_the_command_stops_when_the_dialect_area_file_its_option_names_is_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "places.csv").write_text(places_csv(REPORT_PLACES[:1]), encoding="utf-8")
    write_report_extract(tmp_path / "in.osm.pbf")
    files = path_options(flat_workspace(tmp_path), "names", "dialects", "objects", "areas")
    extracts = [str(tmp_path / "in.osm.pbf"), str(tmp_path / "out.osm.pbf")]
    assert main(["inject", *extracts, *files, "--no-curation", "--dry-run"]) == 1
    assert capsys.readouterr().err == (
        f"dialect area file not found: {tmp_path / 'areas.geojson'}\n"
    )


def test_report_when_no_object_lies_in_a_dialect_area(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    (tmp_path / "osm_objects.json").write_text(
        objects_json(Objects({}, Stamp({}, []))), encoding="utf-8"
    )
    # only the North Sea, found through its QID, far out of every area
    report_run(tmp_path, REPORT_PLACES[2:3], [], areas=Use.IF_PRESENT)
    out = capsys.readouterr().out
    assert out.endswith(
        "objects per dialect area:\n"
        "  (none -- no tagged object lies in a dialect area)\n"
        "\n"
        "(dry run -- nothing written)\n"
    )


# ------------------------------------------------------------- waterways ---
def test_the_member_ways_of_a_matched_waterway_relation_are_found(tmp_path: Path) -> None:
    # the Arlau: the row names the river relation, the labels go on its ways
    nodes: Nodes = {i: ((8.9 + i / 100, 54.6), {}) for i in range(1, 5)}
    path = write_osm(
        tmp_path / "river.osm.pbf",
        nodes=nodes,
        ways={
            10: ([1, 2], {"waterway": "river"}),
            11: ([2, 3], {"waterway": "river"}),
            12: ([3, 4], {"highway": "track"}),
        },
        relations={
            20: (
                [("w", 10, "main_stream"), ("w", 11, "side_stream")],
                {"type": "waterway", "name": "Arlau"},
            ),
            21: ([("w", 12, "")], {"type": "route"}),
        },
    )
    by_id: dict[placelist.Ref, list[placelist.Row]] = {("r", 20): [{}], ("r", 21): [{}]}
    assert inject_names.scan_waterways(str(path), by_id) == {
        ("w", 10): (("r", 20), "Arlau"),
        ("w", 11): (("r", 20), "Arlau"),
    }


def test_a_member_way_inherits_the_frisian_name_of_its_waterway_relation(tmp_path: Path) -> None:
    # the row has a Mooring name only; the river starts in the Nordergoesharde
    # box of AREAS, so OSM's name:frr of the relation is the local name (#81)
    arlau = dict(id="arlou", kind="water", mooring="Arlou", de="Arlau", osm="relation/20")
    (tmp_path / "places.csv").write_text(places_csv([arlau]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_osm(
        tmp_path / "in.osm.pbf",
        nodes={1: ((8.80, 54.66), {}), 2: ((8.82, 54.66), {})},
        ways={10: ([1, 2], {"waterway": "river", "name": "Arlau"})},
        relations={
            20: (
                [("w", 10, "main_stream")],
                {"type": "waterway", "name": "Arlau", "name:frr": "Arluu"},
            )
        },
    )
    curation_file(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        locate_objects(tmp_path)
        inject(tmp_path, areas=Use.IF_PRESENT, curation=Use.IF_PRESENT)
    tags = {(o[0], o[1]): o[2] for o in read_extract(tmp_path / "out.osm.pbf")}
    assert tags[("w", 10)]["frasch:local"] == "Arluu"


# --------------------------------------------------------- QID carriers ---
# a QID reaches more than the row's own object: the place node next to a
# matched boundary, the offshore sea node -- and, mis-tagged in OSM, a shop
# (Rosen-Huus in Friedrichstadt carries the town's QID, #55)
NORDSIIE = dict(id="nordsiie", kind="water", mooring="Nordsiie", de="Nordsee", wikidata="Q1693")


def carrier_tags_after_run(tmp_path: Path, t: str, tags: dict[str, str]) -> dict[str, str]:
    """The tags an object of type `t` carrying the North Sea's QID comes out with."""
    (tmp_path / "places.csv").write_text(places_csv([NORDSIIE]), encoding="utf-8")
    tags = tags | {"name": "Carrier", "wikidata": "Q1693"}
    nodes: Nodes = {1: ((7.5, 54.5), tags if t == "n" else {}), 2: ((7.6, 54.5), {})}
    ways = {10: ([1, 2], tags)} if t == "w" else {}
    relations = {20: ([("n", 1, "")], tags)} if t == "r" else {}
    write_osm(tmp_path / "in.osm.pbf", nodes=nodes, ways=ways, relations=relations)
    curation_file(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        inject(tmp_path, curation=Use.IF_PRESENT)
    out = {(o[0], o[1]): o[2] for o in read_extract(tmp_path / "out.osm.pbf")}
    return out[(t, {"n": 1, "w": 10, "r": 20}[t])]


@pytest.mark.parametrize(
    ("t", "tags"),
    [
        ("n", {"place": "sea"}),
        ("n", {"natural": "peninsula"}),
        ("w", {"natural": "water", "water": "lake"}),
        ("w", {"water": "lake"}),
        ("w", {"waterway": "river"}),
        ("r", {"type": "waterway"}),
        ("r", {"type": "boundary", "boundary": "administrative"}),
        # a landmark that is also a sight: Lange Anna
        ("w", {"natural": "bare_rock", "tourism": "attraction"}),
    ],
)
def test_a_place_like_qid_carrier_gets_the_rows_names(
    tmp_path: Path, t: str, tags: dict[str, str]
) -> None:
    assert carrier_tags_after_run(tmp_path, t, tags)["name:frr-x-mooring"] == "Nordsiie"


def test_a_qid_counts_as_present_whatever_matched_its_carrier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Holm is matched by its id and carries its row's QID; no object
    # carries the North Sea's
    hulm = REPORT_PLACES[0] | {"osm": "node/1"}
    (tmp_path / "places.csv").write_text(places_csv([hulm, NORDSIIE]), encoding="utf-8")
    holm = {"place": "village", "name": "Holm", "wikidata": "Q559369"}
    write_osm(tmp_path / "in.osm.pbf", nodes={1: ((8.9, 54.6), holm)})
    curation_file(tmp_path)
    inject(tmp_path, curation=Use.IF_PRESENT, dry_run=True)
    lines = capsys.readouterr().out.splitlines()
    assert (
        "tagged  1 objects: 1 nodes, 0 ways, 0 relations "
        "(of these 0 matched by wikidata: 1 of 2 QIDs present)"
    ) in lines
    assert "1 wikidata QIDs not present in the file: Q1693 (Nordsiie)" in lines


def test_a_node_found_by_its_qid_is_asked_for_its_own_frisian_name(tmp_path: Path) -> None:
    # no reference, so the objects file does not know it: like its dialect,
    # its Frisian name is the node's own
    hulm = dict(id="hulm", kind="settlement", mooring="Hulm", de="Holm", wikidata="Q559369")
    (tmp_path / "places.csv").write_text(places_csv([hulm]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    (tmp_path / "osm_objects.json").write_text(
        objects_json(Objects({}, Stamp({}, []))), encoding="utf-8"
    )
    holm = {"place": "village", "name": "Holm", "name:frr": "Hoolm", "wikidata": "Q559369"}
    # in the Nordergoesharde box of AREAS
    write_osm(tmp_path / "in.osm.pbf", nodes={1: ((8.85, 54.66), holm)})
    curation_file(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        inject(tmp_path, areas=Use.IF_PRESENT, curation=Use.IF_PRESENT)
    ((_, _, tags, _),) = read_extract(tmp_path / "out.osm.pbf")
    assert tags["frasch:local"] == "Hoolm"


@pytest.mark.parametrize(
    ("t", "tags"),
    [
        ("n", {"shop": "gift"}),
        ("n", {"amenity": "restaurant"}),
        ("w", {"building": "yes"}),
        ("r", {"type": "multipolygon", "landuse": "retail"}),
    ],
)
def test_any_other_qid_carrier_passes_unchanged(
    tmp_path: Path, t: str, tags: dict[str, str]
) -> None:
    assert carrier_tags_after_run(tmp_path, t, tags) == tags | {
        "name": "Carrier",
        "wikidata": "Q1693",
    }
