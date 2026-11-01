"""inject_names.py and its parts (frasch/inject/): the tags an object gets,
a missing input file, and a whole `run()` over a tiny extract written here
with pyosmium.

The extract mirrors real places (ids and positions from the
Schleswig-Holstein extract; ring nodes made up): the village Holm, a
Nordwarft way on Ockholm (the id of the Warft on Habel, moved to where the
row's Nordwarft lies; #135), the Hamburger Hallig relation, the Nordstrand
village node (curated), the Eiderstedt peninsula node and the Oland
coastline way that carry a synthetic square each, Tammensiel (curated, not in the name list), Westerheide on Amrum, a place OSM does not have, and
the Kirchwarft, which no row claims but OSM names in Frisian (#81; moved into
the Mooring box of AREAS)."""

from __future__ import annotations

import collections
import contextlib
import io
import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

from frasch.errors import PipelineError
from frasch import inject_names
from frasch import locate
from frasch import refs
from frasch.__main__ import main
from frasch.geo import LonLat
from frasch.inject import claims, synthetic
from frasch.inject.report import Report
from frasch.inject.stats import SkippedCarrier, Stats
from frasch.objects import Objects, objects_json
from frasch.provenance import Stamp
from conftest import REGISTRY, curation_file, flat_workspace, path_options, places_text
from osm_fixture import (
    Extra,
    ExtractObject,
    Nodes,
    areas_geojson,
    box,
    read_extract,
    ring,
    write_extract,
)


# ------------------------------------------------------------- square_around ---
def test_square_at_the_equator() -> None:
    # 4 km² -> 1 km from the centre to each side; 1 km = 1/111.32 degree
    d = 1 / 111.32
    corners = synthetic.square_around(0.0, 0.0, 4.0)
    assert corners == pytest.approx([(-d, -d), (d, -d), (d, d), (-d, d)])


def test_square_at_sixty_degrees_is_twice_as_wide_in_longitude() -> None:
    # cos 60° = 1/2: a kilometre spans twice the degrees of longitude
    d = 1 / 111.32
    (w, s), (e, _), (_, n), _ = synthetic.square_around(8.0, 60.0, 4.0)
    assert (w, e) == pytest.approx((8.0 - 2 * d, 8.0 + 2 * d))
    assert (s, n) == pytest.approx((60.0 - d, 60.0 + d))


def test_square_is_centred_on_the_node() -> None:
    # Planetiler labels a polygon at its interior point: that must be the node
    corners = synthetic.square_around(8.865286, 54.487378, 50.0)
    assert sum(x for x, _ in corners) / 4 == pytest.approx(8.865286)
    assert sum(y for _, y in corners) / 4 == pytest.approx(54.487378)


# ------------------------------------------------------------ a whole run() ---
HOLM = 240102263
NORDSTRAND = 85929111
EIDERSTEDT = 6337086101
TAMMENSIEL = 355956234
UNTOUCHED_NODE = 240000001
JENSWARFT = 188786563
NORDWARFT = 1347936331
HALLIG_RING = 500000001
OLAND = 1163568825
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
# Oland: its inside point lies in the Mooring box of AREAS, the middle of the
# Hallig -- its curation row's position -- in the Halligfriesisch one
OLAND_NODES = {
    9200000001: (8.855, 54.600),
    9200000002: (8.900, 54.600),
    9200000003: (8.900, 54.620),
    9200000004: (8.855, 54.620),
}
OLAND_CENTRE = (8.857, 54.602)
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
        id="uulonj",
        kind="hallig",
        mooring="Üülönj",
        hallig="Ualöön",
        de="Oland",
        osm=f"way/{OLAND}",
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
        "osm": f"node/{EIDERSTEDT}",
        "name": "Eiderstedt (synthetic landscape polygon)",
        "set_tags": "place=island;frasch:kind=landscape",
        "maxzoom": "10",
        "polygon_km2": "340",
    },
    {
        "osm": f"node/{NORDSTRAND}",
        "name": "Nordstrand (village node)",
        "set_tags": "name:frr-x-mooring=e Strönj;frasch:ref=relation/1420555",
        "minzoom": "12",
    },
    {
        "osm": f"way/{OLAND}",
        "name": "Oland (synthetic island polygon)",
        "lat": str(OLAND_CENTRE[1]),
        "lon": str(OLAND_CENTRE[0]),
        "set_tags": "place=island;frasch:kind=hallig",
        "polygon_km2": "2.1",
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


# Amrum; Ockholm (Nordergoesharde); Reußenköge (Mooring) with the Hamburger
# Hallig (Halligfriesisch) inside it -- the smaller area must win
AREAS = areas_geojson(
    [
        ("frr-x-oomrang", box(8.30, 54.62, 8.40, 54.70)),
        ("frr-x-nordgoes", box(8.78, 54.64, 8.90, 54.70)),
        ("frr-x-mooring", box(8.80, 54.55, 8.95, 54.63)),
        ("frr-x-hallig", box(8.82, 54.58, 8.86, 54.605)),
    ]
)


def write_scene(path: Path) -> None:
    """The extract of the whole run: the villages and Warften of PLACES, the
    Hamburger Hallig and the objects no row names."""
    nodes: dict[int, tuple[LonLat, dict[str, str]]] = {
        NORDSTRAND: ((8.865286, 54.487378), {"place": "village", "name": "Nordstrand"}),
        EIDERSTEDT: ((8.79035, 54.35), {"natural": "peninsula", "name": "Eiderstedt"}),
        HOLM: ((8.866668, 54.833305), {"place": "village", "name": "Holm", "wikidata": "Q559369"}),
        UNTOUCHED_NODE: ((8.9, 54.6), {"place": "village", "name": "Bredstedt"}),
        TAMMENSIEL: ((8.7033, 54.7433), {"place": "hamlet", "name": "Tammensiel"}),
        KIRCHWARFT: (
            (8.88, 54.56),
            {"place": "hamlet", "name": "Kirchwarft", "name:frr": "Schörkeweerw"},
        ),
        PINNEBERG: ((9.80, 53.66), {"place": "town", "name": "Pinneberg", "name:frr": "Pinebärj"}),
    }
    for ring_nodes in (NORDWARFT_NODES, JENSWARFT_NODES, HALLIG_NODES, OLAND_NODES):
        nodes.update({i: (loc, {}) for i, loc in ring_nodes.items()})

    def closed(ring_nodes: Mapping[int, LonLat]) -> list[int]:
        return [*ring_nodes, next(iter(ring_nodes))]

    hallig_boundary = [("w", HALLIG_RING, "outer")]
    write_extract(
        path,
        nodes,
        {
            JENSWARFT: (
                closed(JENSWARFT_NODES),
                {"name": "Jenswarft", "name:frr": "Jenswäärw", "landuse": "residential"},
            ),
            HALLIG_RING: (closed(HALLIG_NODES), {"natural": "coastline"}),
            OLAND: (
                closed(OLAND_NODES),
                {"natural": "coastline", "place": "island", "name": "Oland", "name:frr": "Ualöön"},
            ),
            UNTOUCHED_WAY: ([NORDSTRAND, HOLM], {"highway": "track"}),
            NORDWARFT: (
                closed(NORDWARFT_NODES),
                {"name": "Nordwarft", "name:frr": "Nöördweerew", "landuse": "residential"},
            ),
        },
        {
            KREIS: (
                hallig_boundary,
                {
                    "type": "boundary",
                    "boundary": "administrative",
                    "admin_level": "6",
                    "name": "Kreis Nordfriesland",
                    "name:de": "Nordfriesland",
                    "name:frr": "Nuurdfresklun",
                },
            ),
            HAMBURGER_HALLIG: (
                hallig_boundary,
                {
                    "type": "boundary",
                    "boundary": "administrative",
                    "admin_level": "10",
                    "name": "Hamburger Hallig",
                    "name:frr": "Hamborjer Hali",
                },
            ),
        },
    )


# the objects in file order, and by (type letter, id)
Injected = tuple[list[ExtractObject], dict[tuple[str, int], tuple[dict[str, str], Extra]]]


NO_AREAS = areas_geojson([])


def run(d: Path, *, dry_run: bool = False) -> Report:
    """Inject the name files of `d` into its in.osm.pbf, as out.osm.pbf."""
    return inject_names.run(
        flat_workspace(d),
        REGISTRY,
        str(d / "in.osm.pbf"),
        str(d / "out.osm.pbf"),
        dry_run=dry_run,
    )


def locate_objects(d: Path, *more: Path) -> None:
    """Write the objects file of `d` from its in.osm.pbf, and the extracts
    `more`."""
    with contextlib.redirect_stdout(io.StringIO()):
        locate.run(flat_workspace(d), REGISTRY, [d / "in.osm.pbf", *more])


def fill_in(d: Path) -> None:
    """Write what a test has not written of the files a run needs besides
    the name list and the extract: no dialect areas, nothing curated, the
    objects located in the extract."""
    if not (d / "areas.geojson").exists():
        (d / "areas.geojson").write_text(json.dumps(NO_AREAS), encoding="utf-8")
    if not (d / "curation.csv").exists():
        curation_file(d)
    if not (d / "osm_objects.json").exists():
        locate_objects(d)


def inject(d: Path, *, dry_run: bool = False) -> Report:
    """`run`, with the inputs the test has not written filled in (`fill_in`)."""
    fill_in(d)
    return run(d, dry_run=dry_run)


def extracts(d: Path) -> list[str]:
    """The extract a command reads in `d` and the one it writes."""
    return [str(d / "in.osm.pbf"), str(d / "out.osm.pbf")]


def input_options(d: Path) -> list[str]:
    """What points `frasch inject` at the name files of `d`."""
    return path_options(flat_workspace(d), "names", "dialects", "areas", "objects", "curation")


def normalized(text: str, directory: Path) -> str:
    """`text` with the run's directory as `<dir>`."""
    return text.replace(str(directory), "<dir>")


@pytest.fixture(scope="module")
def injected_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Stats]:
    """-> (the run's directory, what it counted)"""
    d = tmp_path_factory.mktemp("inject")
    (d / "places.csv").write_text(places_text(PLACES), encoding="utf-8")
    curation_file(d, *CURATION)
    (d / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_scene(d / "in.osm.pbf")
    return d, inject(d).stats


@pytest.fixture(scope="module")
def injected(injected_run: tuple[Path, Stats]) -> Injected:
    d, _ = injected_run
    objs = read_extract(d / "out.osm.pbf")
    return objs, {(t, i): (tags, extra) for t, i, tags, extra in objs}


@pytest.fixture(scope="module")
def stats(injected_run: tuple[Path, Stats]) -> Stats:
    _, counted = injected_run
    return counted


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
        ("n", EIDERSTEDT),
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
    (tmp_path / "places.csv").write_text(places_text([PLACES[0]]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    (tmp_path / "osm_objects.json").write_text(
        objects_json(Objects({}, Stamp({}, []))), encoding="utf-8"
    )
    write_scene(tmp_path / "in.osm.pbf")
    with pytest.raises(PipelineError, match=f"node/{HOLM} is not located yet"):
        inject(tmp_path)
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
def test_an_object_no_row_claims_gets_osms_frisian_name_as_its_local_one_with_its_area(
    injected: Injected,
) -> None:
    _, by_key = injected
    assert by_key[("n", KIRCHWARFT)][0] == {
        "place": "hamlet",
        "name": "Kirchwarft",
        "name:frr": "Schörkeweerw",
        "frasch:local": "Schörkeweerw",
        "frasch:dialect": "frr-x-mooring",
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


def square_of(
    injected: Injected, stats: Stats, key: tuple[str, int]
) -> tuple[dict[str, str], list[LonLat]]:
    """The tags and corners of the synthetic square curation puts on the
    object `key`."""
    _, by_key = injected
    (way_id,) = [square.way_id for square in stats.added_squares if square.key == key]
    tags, node_ids = by_key[("w", way_id)]
    assert isinstance(node_ids, list)
    return tags, [loc for i in node_ids[:-1] if isinstance(loc := by_key[("n", i)][1], tuple)]


def test_each_synthetic_square_is_a_new_closed_way_through_four_new_nodes(
    injected: Injected,
) -> None:
    _, by_key = injected
    squares = new_objects(by_key, "w", MAX_WAY)
    assert [wid for wid, _ in squares] == [MAX_WAY + 1, MAX_WAY + 2]
    corners = [nid for nid, _ in new_objects(by_key, "n", MAX_NODE + 1)]
    assert [refs for _, (_, refs) in squares] == [
        corners[:4] + corners[:1],
        corners[4:] + corners[4:5],
    ]


def test_synthetic_square_nodes_are_written_as_untagged_nodes(injected: Injected) -> None:
    _, by_key = injected
    corners = new_objects(by_key, "n", MAX_NODE + 1)
    assert len(corners) == 8
    assert all(tags == {} for _, (tags, _) in corners)


def test_synthetic_square_is_340_km2_around_the_peninsula_node(
    injected: Injected, stats: Stats
) -> None:
    _, corners = square_of(injected, stats, ("n", EIDERSTEDT))
    lon = sum(x for x, _ in corners) / 4
    lat = sum(y for _, y in corners) / 4
    assert (lon, lat) == pytest.approx((8.79035, 54.35), abs=1e-6)
    side_ns = (max(y for _, y in corners) - min(y for _, y in corners)) * 111.32
    side_ew = (
        (max(x for x, _ in corners) - min(x for x, _ in corners))
        * 111.32
        * math.cos(math.radians(54.35))
    )
    assert side_ns == pytest.approx(math.sqrt(340), rel=1e-4)
    assert side_ew == pytest.approx(math.sqrt(340), rel=1e-4)


def test_synthetic_square_carries_the_nodes_names_and_its_own_tags(
    injected: Injected, stats: Stats
) -> None:
    # the name from the node; place/kind/maxzoom from the polygon row
    tags, _ = square_of(injected, stats, ("n", EIDERSTEDT))
    assert tags == {
        "name": "Eiderstedt",
        "place": "island",
        "frasch:kind": "landscape",
        "frasch:maxzoom": "10",
        "frasch:square": "yes",
    }


def test_a_square_on_a_way_is_centred_on_its_rows_position(
    injected: Injected, stats: Stats
) -> None:
    _, corners = square_of(injected, stats, ("w", OLAND))
    lon = sum(x for x, _ in corners) / 4
    lat = sum(y for _, y in corners) / 4
    assert (lon, lat) == pytest.approx(OLAND_CENTRE, abs=1e-6)


def test_a_square_on_a_way_carries_the_ways_names_and_its_own_tags(
    injected: Injected, stats: Stats
) -> None:
    # OSM's names and the row's, and the dialect and local name of where the
    # square is; place and kind from its curation row
    tags, _ = square_of(injected, stats, ("w", OLAND))
    assert tags == {
        "name": "Oland",
        "name:frr": "Ualöön",
        "name:frr-x-mooring": "Üülönj",
        "name:frr-x-hallig": "Ualöön",
        "name:de": "Oland",
        "frasch:dialect": "frr-x-hallig",
        "frasch:local": "Ualöön",
        "frasch:ref": "uulonj",
        "place": "island",
        "frasch:kind": "hallig",
        "frasch:square": "yes",
    }


def test_a_way_with_a_square_gives_up_its_place_label_and_keeps_its_other_tags(
    injected: Injected,
) -> None:
    # its square has the label; the coastline stays, with its names, which
    # are those of where its square is
    _, by_key = injected
    tags, _ = by_key[("w", OLAND)]
    assert tags == {
        "natural": "coastline",
        "name": "Oland",
        "name:frr": "Ualöön",
        "name:frr-x-mooring": "Üülönj",
        "name:frr-x-hallig": "Ualöön",
        "name:de": "Oland",
        "frasch:kind": "hallig",
        "frasch:dialect": "frr-x-hallig",
        "frasch:local": "Ualöön",
        "frasch:ref": "uulonj",
    }


def test_a_square_on_a_relation_carries_the_relations_names(tmp_path: Path) -> None:
    # Nordstrand: the municipality relation, its square on the village
    ring_nodes, ring_ids = ring(1, *box(8.80, 54.48, 8.90, 54.54))
    write_extract(
        tmp_path / "in.osm.pbf",
        nodes=ring_nodes,
        ways={10: (ring_ids, {})},
        relations={
            1420555: (
                [("w", 10, "outer")],
                {"type": "boundary", "boundary": "administrative", "name": "Nordstrand"},
            )
        },
    )
    (tmp_path / "places.csv").write_text(
        places_text(
            [dict(id="e-stronj", kind="island", mooring="e Strönj", osm="relation/1420555")]
        ),
        encoding="utf-8",
    )
    curation_file(
        tmp_path,
        {
            "osm": "relation/1420555",
            "lat": "54.4873775",
            "lon": "8.8652863",
            "set_tags": "place=island",
            "polygon_km2": "50",
        },
    )
    (square,) = inject(tmp_path).stats.added_squares
    by_key = {(t, i): tags for t, i, tags, _ in read_extract(tmp_path / "out.osm.pbf")}
    assert by_key[("w", square.way_id)] == {
        "name": "Nordstrand",
        "name:frr-x-mooring": "e Strönj",
        "frasch:ref": "e-stronj",
        "place": "island",
        "frasch:square": "yes",
    }


# ------------------------------------------------- what the run counted ---
def test_the_objects_a_row_tags_are_counted_by_type(stats: Stats) -> None:
    # Holm and the node added for Westerheide, the Nordwarft and Oland, the
    # Hamburger Hallig and the Kreis -- not what curation alone or OSM's
    # name:frr tags
    assert stats.tagged == collections.Counter(n=2, w=2, r=2)


def test_the_names_written_are_counted_per_key(stats: Stats) -> None:
    assert stats.names == collections.Counter(
        {
            "name:frr-x-mooring": 5,
            "name:de": 5,
            "name:frr-x-nordgoes": 2,
            "name:frr-x-oomrang": 1,
            "name:frr-x-hallig": 1,
        }
    )


def test_the_tagged_objects_are_counted_per_dialect(stats: Stats) -> None:
    # Holm and the Kreis lie in no dialect area; Oland where its square is
    assert stats.dialects == collections.Counter(
        {"frr-x-oomrang": 1, "frr-x-nordgoes": 1, "frr-x-hallig": 2}
    )


def test_the_local_forms_rows_give_are_counted(stats: Stats) -> None:
    # the Nordwarft, the Hamburger Hallig, Oland, Westerheide
    assert stats.local == 4


def test_the_local_forms_rows_take_from_osms_frisian_name_are_counted(stats: Stats) -> None:
    # the Hamburger Hallig
    assert stats.osm_local_claimed == 1


def test_osms_frisian_names_on_objects_no_row_claims_are_counted(stats: Stats) -> None:
    # the Kirchwarft and the Jenswarft
    assert stats.osm_local_unclaimed == 2


def test_the_added_node_is_recorded_with_its_local_reference(stats: Stats) -> None:
    assert [(point.node_id, point.key) for point in stats.added_points] == [
        (MAX_NODE + 1, ("l", "westerheide-amrum"))
    ]


def test_the_synthetic_square_is_recorded_with_its_curation_row(stats: Stats) -> None:
    assert [(square.key, square.label, square.km2) for square in stats.added_squares] == [
        (("w", OLAND), "Oland (synthetic island polygon)", 2.1),
        (("n", EIDERSTEDT), "Eiderstedt (synthetic landscape polygon)", 340.0),
    ]


# ------------------------------------- rows that do not fit the extract ---
# a dry run over a second extract, for what a run counts of rows and
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
    write_extract(
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


def write_report_inputs(
    d: Path, places: Iterable[Mapping[str, str]], curation: Iterable[Mapping[str, str]]
) -> None:
    """The name list, the curation and the report extract.  The objects are
    located in that extract and in a second one, which holds Bredstedt: the
    row that names it is in the objects file, its object not in the extract
    the run tags."""
    (d / "places.csv").write_text(places_text(places), encoding="utf-8")
    write_report_extract(d / "in.osm.pbf")
    curation_file(d, *curation)
    elsewhere = write_extract(
        d / "elsewhere.osm.pbf", nodes={99: ((8.97, 54.62), {"place": "town", "name": "Bredstedt"})}
    )
    locate_objects(d, elsewhere)


def report_run(
    d: Path, places: Iterable[Mapping[str, str]], curation: Iterable[Mapping[str, str]]
) -> Report:
    """A dry run over the report extract, without dialect areas unless the
    test has written some."""
    write_report_inputs(d, places, curation)
    return inject(d, dry_run=True)


@pytest.fixture(scope="module")
def misfits(tmp_path_factory: pytest.TempPathFactory) -> Stats:
    """What the dry run over the report extract with REPORT_PLACES and
    REPORT_CURATION counted."""
    return report_run(tmp_path_factory.mktemp("misfits"), REPORT_PLACES, REPORT_CURATION).stats


def test_every_object_of_the_extract_is_scanned(misfits: Stats) -> None:
    # six nodes, two ways, one relation
    assert misfits.scanned == 9


def test_only_the_references_the_extract_has_are_found(misfits: Stats) -> None:
    # not Bredstedt, node/99, which lies in the other extract
    assert misfits.found == {("n", 1), ("r", 20), ("l", "sophien-koog")}


def test_an_object_tagged_through_its_qid_alone_is_counted(misfits: Stats) -> None:
    # the North Sea
    assert misfits.qid_carriers == 1


def test_a_same_named_member_way_of_a_waterway_is_counted(misfits: Stats) -> None:
    # the Arlau's way 10, not the Alte Arlau
    assert misfits.member_ways == 1


def test_a_qid_carrier_that_is_not_place_like_is_recorded(misfits: Stats) -> None:
    assert misfits.skipped_carriers == [SkippedCarrier(("n", 6), "Rosen-Huus", "Q559369")]


def test_only_the_curated_objects_the_extract_has_are_recorded(misfits: Stats) -> None:
    # not node/98
    assert misfits.curated == {("n", 1)}


def test_no_square_is_added_around_a_node_the_extract_lacks(misfits: Stats) -> None:
    # the Sophien-Koog's square, not the one around node/97
    assert [square.key for square in misfits.added_squares] == [("l", "sophien-koog")]


def test_the_report_spells_no_reference_by_its_type_letter(tmp_path: Path) -> None:
    # node/6, not n/6: the one form the cells of the lists have
    log = report_run(tmp_path, REPORT_PLACES, REPORT_CURATION).log
    assert [line for line in log if re.search(r"\b[nwr]/\d", line)] == []


def test_a_run_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_run(tmp_path, REPORT_PLACES, REPORT_CURATION)
    assert capsys.readouterr().out == ""


def test_the_command_prints_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "places.csv").write_text(places_text(REPORT_PLACES[:1]), encoding="utf-8")
    write_report_extract(tmp_path / "in.osm.pbf")
    fill_in(tmp_path)
    main(["inject", *extracts(tmp_path), *input_options(tmp_path), "--dry-run"])
    assert capsys.readouterr().out.endswith("\n(dry run -- nothing written)\n")


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    report_run(tmp_path, REPORT_PLACES[:1], [])
    assert not (tmp_path / "out.osm.pbf").exists()


def test_a_local_reference_without_a_position_stops_the_build(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as exc:
        report_run(tmp_path, REPORT_PLACES, REPORT_CURATION[:3])
    assert normalized(str(exc.value), tmp_path) == (
        "1 local reference(s) in <dir>/places.csv have no row with lat/lon in "
        "<dir>/curation.csv:\n"
        "  local/sophien-koog  Sofiinkuuch (Sophien-Koog) (places.csv line 6)"
    )


# a file the run needs, and what it says when the file is not there
MISSING_INPUTS = [
    ("areas.geojson", "<dir>/areas.geojson not found -- build it with `just rebuild areas`"),
    (
        "osm_objects.json",
        "<dir>/osm_objects.json not found -- build it with `just rebuild objects`",
    ),
    ("curation.csv", "curation file not found: <dir>/curation.csv"),
]


def write_inputs_without(d: Path, file: str) -> None:
    """Every input of a run over the report extract but `file`."""
    write_report_inputs(d, REPORT_PLACES[:1], [])
    fill_in(d)
    (d / file).unlink()


@pytest.mark.parametrize(("file", "message"), MISSING_INPUTS)
def test_a_missing_input_file_stops_the_run_and_is_named(
    tmp_path: Path, file: str, message: str
) -> None:
    write_inputs_without(tmp_path, file)
    with pytest.raises(PipelineError) as exc:
        run(tmp_path)
    assert normalized(str(exc.value), tmp_path) == message


@pytest.mark.parametrize("file", [file for file, _ in MISSING_INPUTS])
def test_a_run_without_an_input_file_writes_nothing(tmp_path: Path, file: str) -> None:
    write_inputs_without(tmp_path, file)
    with pytest.raises(PipelineError):
        run(tmp_path)
    assert not (tmp_path / "out.osm.pbf").exists()


def test_the_command_stops_on_a_missing_dialect_area_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_inputs_without(tmp_path, "areas.geojson")
    assert main(["inject", *extracts(tmp_path), *input_options(tmp_path)]) == 1
    assert capsys.readouterr().err == (
        f"{tmp_path / 'areas.geojson'} not found -- build it with `just rebuild areas`\n"
    )


def test_an_object_outside_every_dialect_area_counts_for_no_dialect(tmp_path: Path) -> None:
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    # only the North Sea, found through its QID, far out of every area
    assert report_run(tmp_path, REPORT_PLACES[1:2], []).stats.dialects == collections.Counter()


# ------------------------------------------------------------- waterways ---
def test_the_member_ways_of_a_matched_waterway_relation_are_found(tmp_path: Path) -> None:
    # the Arlau: the row names the river relation, the labels go on its ways
    nodes: Nodes = {i: ((8.9 + i / 100, 54.6), {}) for i in range(1, 5)}
    path = write_extract(
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
    claimed: list[refs.Ref] = [("r", 20), ("r", 21)]
    assert claims.scan_waterways(str(path), claimed) == {
        ("w", 10): (("r", 20), "Arlau"),
        ("w", 11): (("r", 20), "Arlau"),
    }


def test_a_member_way_inherits_the_frisian_name_of_its_waterway_relation(tmp_path: Path) -> None:
    # the row has a Mooring name only; the river starts in the Nordergoesharde
    # box of AREAS, so OSM's name:frr of the relation is the local name (#81)
    arlau = dict(id="arlou", kind="water", mooring="Arlou", de="Arlau", osm="relation/20")
    (tmp_path / "places.csv").write_text(places_text([arlau]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_extract(
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
    inject(tmp_path)
    tags = {(o[0], o[1]): o[2] for o in read_extract(tmp_path / "out.osm.pbf")}
    assert tags[("w", 10)]["frasch:local"] == "Arluu"


# --------------------------------------------------------- QID carriers ---
# a QID reaches more than the row's own object: the place node next to a
# matched boundary, the offshore sea node -- and, mis-tagged in OSM, a shop
# (Rosen-Huus in Friedrichstadt carries the town's QID, #55)
NORDSIIE = dict(id="nordsiie", kind="water", mooring="Nordsiie", de="Nordsee", wikidata="Q1693")


def carrier_tags_after_run(tmp_path: Path, t: str, tags: dict[str, str]) -> dict[str, str]:
    """The tags an object of type `t` carrying the North Sea's QID comes out with."""
    (tmp_path / "places.csv").write_text(places_text([NORDSIIE]), encoding="utf-8")
    tags = tags | {"name": "Carrier", "wikidata": "Q1693"}
    nodes: Nodes = {1: ((7.5, 54.5), tags if t == "n" else {}), 2: ((7.6, 54.5), {})}
    ways = {10: ([1, 2], tags)} if t == "w" else {}
    relations = {20: ([("n", 1, "")], tags)} if t == "r" else {}
    write_extract(tmp_path / "in.osm.pbf", nodes=nodes, ways=ways, relations=relations)
    inject(tmp_path)
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


def test_a_qid_counts_as_present_whatever_matched_its_carrier(tmp_path: Path) -> None:
    # Holm is matched by its id and carries its row's QID; no object
    # carries the North Sea's
    hulm = REPORT_PLACES[0] | {"osm": "node/1"}
    (tmp_path / "places.csv").write_text(places_text([hulm, NORDSIIE]), encoding="utf-8")
    holm = {"place": "village", "name": "Holm", "wikidata": "Q559369"}
    write_extract(tmp_path / "in.osm.pbf", nodes={1: ((8.9, 54.6), holm)})
    assert inject(tmp_path, dry_run=True).stats.present_qids == {"Q559369"}


def test_a_node_found_by_its_qid_is_asked_for_its_own_frisian_name(tmp_path: Path) -> None:
    # no reference, so the objects file does not know it: like its dialect,
    # its Frisian name is the node's own
    hulm = dict(id="hulm", kind="settlement", mooring="Hulm", de="Holm", wikidata="Q559369")
    (tmp_path / "places.csv").write_text(places_text([hulm]), encoding="utf-8")
    (tmp_path / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    holm = {"place": "village", "name": "Holm", "name:frr": "Hoolm", "wikidata": "Q559369"}
    # in the Nordergoesharde box of AREAS
    write_extract(tmp_path / "in.osm.pbf", nodes={1: ((8.85, 54.66), holm)})
    inject(tmp_path)
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
