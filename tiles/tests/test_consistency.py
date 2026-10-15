"""The map and the search index agree (#24): one tiny extract is located
(`frasch build objects`), injected (`frasch inject`) and exported
(`frasch build index`), and every feature that carries a `frasch:ref`
must say what that row's search entry says -- the same dialect, the same
local name, the same German name and, for a node, the same position (a way
or relation has no label point before Planetiler places one).  Planetiler
passes the frasch:* and name:* tags through verbatim, so the injected
extract stands in for the tiles here; `frasch check-tiles` compares real tiles the
same way.

The places are the kinds that disagreed before: an island whose vertex
average lies in the sea (Sylt, Amrum), a node near a dialect border
(Stiardebel), a Kreis, a place whose inside point misses its area while its
outline hits it (Oland), and a row with two objects in two areas
(Nordwärw).  And the places whose local name may be OSM's own `name:frr`
(#81): one in an area whose row has no local name (Slütsil), one whose row
has one (Oland), one outside every area (Kil).

The labels of the place card's listed scenarios come from here too: what
the entry and the injected object of each of LISTED_SCENARIOS say is
committed as web/src/testing/generated/listedScenarios.json, which
web/src/mapCardConsistency.test.ts checks the card and the map label
against.  A test here fails when that file is not what the pipeline gives
now; `uv run pytest tiles/tests/test_consistency.py --write-scenarios`
rewrites it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import osmium
import pytest

from frasch import check_tiles
from frasch import inject_names
from frasch import locate
from frasch import refs
from frasch import searchindex
from frasch.check_tiles import Label, PropValue
from frasch.geo import LonLat
from frasch.paths import ROOT
from frasch.placenames import SearchEntry
from conftest import REGISTRY, flat_workspace, places_text
from osm_fixture import ring, write_extract

# the search entries by id, and the injected extract's labelled features
Built = tuple[dict[str, SearchEntry], list[Label]]

# U-shaped Sylt: the mean of its corners lies in the bay, outside its area
SYLT = [
    (8.0, 54.0),
    (9.0, 54.0),
    (9.0, 55.0),
    (8.8, 55.0),
    (8.8, 54.2),
    (8.2, 54.2),
    (8.2, 55.0),
    (8.0, 55.0),
]
SYLT_NODES, SYLT_RING = ring(100, *SYLT)
# Oland: its inside point lies east of the Langeneß strip, its first vertex in it
OLAND_NODES, OLAND_RING = ring(200, (9.50, 54.60), (9.70, 54.60), (9.70, 54.62), (9.50, 54.62))
NODES = (
    {
        1: ((9.25, 54.5), {"name": "Stadum"}),  # Stiardebel
        2: ((9.35, 54.5), {"name": "Nordwarft"}),  # Nordwärw's node
        3: ((9.15, 54.5), {"place": "village", "name": "Ockholm", "wikidata": "Q1"}),  # only by QID
        4: ((9.15, 54.45), {}),  # Nordwärw's way starts here
        5: ((9.12, 54.5), {"name": "Schlüttsiel", "name:frr": "Slütsiil"}),
        6: ((10.0, 54.0), {"name": "Kiel", "name:frr": "Kil"}),
        # the places of the card's listed scenarios
        7: ((9.3, 55.0), {"place": "village", "name": "Tinglev", "name:da": "Tinglev"}),
        8: ((8.5, 55.2), {}),  # Listlai: no name of OSM's own
        9: ((9.0, 55.3), {"name:de": "Seth"}),
        13: (
            (9.15, 54.42),
            {"place": "islet", "name": "Hamburger Hallig", "name:frr": "Hamborjer Hali"},
        ),
        14: ((9.7, 54.85), {"name": "Wisch"}),  # e Wäsk, in its area
        15: ((10.2, 54.2), {"name": "Wisch"}),  # e Wäsk, outside every area
        16: ((9.4, 54.42), {"name": "Nordwarft", "name:frr": "Nöördweerew"}),  # on the Hallig
        17: ((9.12, 54.42), {"name": "Nordwarft"}),  # Noordweerw, in Nordergoesharde
    }
    | SYLT_NODES
    | OLAND_NODES
)
WAYS = {
    10: (SYLT_RING, {"natural": "coastline"}),
    11: (OLAND_RING, {"place": "island", "name:frr": "Ualöön"}),
    12: ([4, 2], {"landuse": "residential"}),
}  # Nordwärw's way
RELATIONS = {
    20: ([("w", 10, "outer")], {"type": "multipolygon", "place": "island"}),
    27019: (
        [("w", 10, "outer")],
        {"type": "boundary", "boundary": "administrative", "admin_level": "6"},
    ),
}
ROWS = [
    {
        "id": "sol",
        "kind": "island",
        "mooring": "Söl",
        "solring": "Söl",
        "de": "Sylt",
        "osm": "relation/20",
    },
    {
        "id": "stiardebel",
        "kind": "settlement",
        "mooring": "Stiirdebel",
        "nordgoes": "Steerdebel",
        "suedgoes": "Stiardebel",
        "osm": "node/1",
    },
    {
        "id": "kris",
        "kind": "landscape",
        "mooring": "Kris",
        "nordgoes": "Krais",
        "osm": "relation/27019",
    },
    {"id": "olun", "kind": "hallig", "mooring": "Olun", "hallig": "Ualöönj", "osm": "way/11"},
    {
        "id": "nordwarw",
        "kind": "warft",
        "mooring": "Nordwärw",
        "nordgoes": "Noordweerw",
        "hallig": "Nordwärw",
        "osm": "way/12; node/2",
    },
    {"id": "hulm", "kind": "settlement", "mooring": "Hulm", "wikidata": "Q1"},
    {"id": "slutsil", "kind": "warft", "mooring": "Slütsil", "osm": "node/5"},
    {"id": "kil", "kind": "settlement", "mooring": "Kil", "osm": "node/6"},
    {
        "id": "tingle",
        "kind": "settlement",
        "wieding": "Tingle",
        "de": "Tingleff",
        "da": "Tinglev",
        "osm": "node/7",
    },
    {
        "id": "listlai",
        "kind": "settlement",
        "solring": "Listlai",
        "de": "Lister Ley",
        "osm": "node/8",
    },
    {"id": "satj", "kind": "settlement", "mooring": "Sätj", "wieding": "Säit", "osm": "node/9"},
    {
        "id": "hamborjer-hali",
        "kind": "hallig",
        "mooring": "Hamborjer Håli",
        "de": "Hamburger Hallig",
        "osm": "node/13",
    },
    {
        "id": "e-wask",
        "kind": "settlement",
        "wieding": "e Wäsk",
        "de": "Wisch",
        "osm": "node/14; node/15",
    },
    {
        "id": "noordweerw",
        "kind": "warft",
        "mooring": "Nordwärw",
        "nordgoes": "Noordweerw",
        "de": "Nordwarft",
        "osm": "node/16; node/17",
    },
]


def box(west: float, south: float, east: float, north: float) -> list[LonLat]:
    return [(west, south), (east, south), (east, north), (west, north)]


AREAS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"dialect": tag},
            "geometry": {"type": "Polygon", "coordinates": [corners + corners[:1]]},
        }
        for tag, corners in [
            ("frr-x-solring", SYLT),
            ("frr-x-nordgoes", box(9.1, 54.4, 9.3, 54.6)),
            ("frr-x-suedgoes", box(9.2, 54.4, 9.3, 54.6)),
            ("frr-x-hallig", box(9.3, 54.4, 9.45, 54.6)),
            ("frr-x-hallig", box(9.45, 54.59, 9.55, 54.63)),
            ("frr-x-wieding", box(9.6, 54.8, 9.8, 54.9)),
        ]
    ],
}


def injected_features(pbf: Path) -> list[Label]:
    """The injected extract's labelled objects, as check_tiles reads tiles."""
    out: list[Label] = []
    for o in osmium.FileProcessor(str(pbf)):
        if "frasch:ref" not in o.tags:
            continue
        feature: Label = {
            "osm": refs.format([(o.type_str(), o.id)]),
            "props": dict(o.tags),
        }
        if isinstance(o, osmium.osm.Node):
            feature |= {"lon": o.location.lon, "lat": o.location.lat}
        out.append(feature)
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    d = tmp_path_factory.mktemp("consistency")
    (d / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    (d / "curation.csv").write_text(
        "osm,name,lat,lon,set_tags,minzoom,maxzoom,polygon_km2,note\n", encoding="utf-8"
    )
    (d / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    write_extract(d / "in.osm.pbf", NODES, WAYS, RELATIONS)
    ws = flat_workspace(d)
    locate.run(ws, REGISTRY, [d / "in.osm.pbf"])
    inject_names.run(ws, REGISTRY, str(d / "in.osm.pbf"), str(d / "out.osm.pbf"))
    searchindex.run(ws, REGISTRY)
    names = json.loads((d / "names.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in names["places"]}, injected_features(d / "out.osm.pbf")


def test_tiles_and_search_index_agree_on_every_ref(built: Built) -> None:
    entries, features = built
    assert check_tiles.compare(entries, features, REGISTRY) == []


def test_every_row_on_the_map_is_checked(built: Built) -> None:
    entries, features = built
    assert {f["props"]["frasch:ref"] for f in features} == {
        "sol",
        "stiardebel",
        "kris",
        "olun",
        "nordwarw",
        "hulm",
        "slutsil",
        "kil",
        *LISTED_REFS,
    }
    # keyed by its QID alone: on the map, but without a position to search
    assert set(entries) == {
        "sol",
        "stiardebel",
        "kris",
        "olun",
        "nordwarw",
        "slutsil",
        "kil",
        *LISTED_REFS,
    }


@pytest.mark.parametrize(
    "ref, dialect, local",
    [
        ("sol", "frr-x-solring", "Söl"),
        ("stiardebel", "frr-x-suedgoes", "Stiardebel"),
        ("kris", None, None),
        ("olun", "frr-x-hallig", "Ualöönj"),
        ("nordwarw", "frr-x-nordgoes", "Noordweerw"),
        ("slutsil", "frr-x-nordgoes", "Slütsiil"),
        ("kil", None, None),
    ],
)
def test_the_search_entry_has_the_dialect_of_where_the_place_is(
    built: Built, ref: str, dialect: str | None, local: str | None
) -> None:
    entries, _ = built
    assert (entries[ref].get("dialect"), entries[ref].get("local")) == (dialect, local)


# ------------------------------------------- the card's listed scenarios ---
# A clicked label of a listed place, as web/src/mapCardConsistency.test.ts
# names it: the row, and the object of it that is clicked.
LISTED_SCENARIOS = {
    "a listed Danish place whose German name only the list has": ("tingle", "node/7"),
    "a listed place whose object has no generic OSM name": ("listlai", "node/8"),
    "a listed place with only OSM’s German name and no generic OSM name": ("satj", "node/9"),
    # #81: the row has no name in the dialect of its area, so the local name
    # is OSM's `name:frr`, ahead of another dialect's
    "a listed place whose local name is OSM’s Frisian one": ("hamborjer-hali", "node/13"),
    # the entry stands for the row's first object, on the Hallig, whose local
    # name is OSM's; the clicked one lies in another dialect area
    "the second object of a listed row, in another dialect area": ("noordweerw", "node/17"),
    # #89: the entry's object has a local name, the clicked one, outside
    # every dialect area, has none
    "the second object of a listed row, outside every dialect area": ("e-wask", "node/15"),
}
LISTED_REFS = {ref for ref, _ in LISTED_SCENARIOS.values()}
SCENARIOS_JSON = Path(ROOT) / "web" / "src" / "testing" / "generated" / "listedScenarios.json"


class ClickedLabel(TypedDict):
    """A listed scenario: the place's search entry, and what the tiles say of
    the clicked object."""

    entry: SearchEntry
    props: dict[str, PropValue]


def tile_props(label: Label) -> dict[str, PropValue]:
    """What Planetiler carries of an injected object's tags into the tiles:
    its names and the frasch:* attributes."""
    return {
        key: value
        for key, value in label["props"].items()
        if key == "name" or key.startswith(("name:", "frasch:"))
    }


def listed_scenarios(built: Built) -> dict[str, ClickedLabel]:
    entries, features = built
    by_object = {f["osm"]: f for f in features}
    return {
        scenario: {"entry": entries[ref], "props": tile_props(by_object[osm])}
        for scenario, (ref, osm) in LISTED_SCENARIOS.items()
    }


def scenarios_text(scenarios: dict[str, ClickedLabel]) -> str:
    return json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n"


def test_every_listed_scenario_is_a_feature_of_its_row(built: Built) -> None:
    _, features = built
    labelled = {(f["props"]["frasch:ref"], f["osm"]) for f in features}
    assert set(LISTED_SCENARIOS.values()) <= labelled


def test_the_committed_listed_scenarios_are_what_the_pipeline_gives(
    built: Built, request: pytest.FixtureRequest
) -> None:
    text = scenarios_text(listed_scenarios(built))
    if request.config.getoption("--write-scenarios"):
        SCENARIOS_JSON.parent.mkdir(parents=True, exist_ok=True)
        SCENARIOS_JSON.write_text(text, encoding="utf-8")
    committed = SCENARIOS_JSON.read_text(encoding="utf-8") if SCENARIOS_JSON.exists() else ""
    assert committed == text, (
        f"{SCENARIOS_JSON.relative_to(ROOT)} is not what the pipeline gives now: "
        "rewrite it with `uv run pytest tiles/tests/test_consistency.py --write-scenarios`, "
        "then run mapCardConsistency.test.ts (cd web && npm test)"
    )
