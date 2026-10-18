"""frasch/inject/report.py: the lines a run of the injector prints, each
part on its own, from inputs and counts built here.  What a run counts is
tested in test_inject_names.py."""

from __future__ import annotations

import collections
from dataclasses import replace

import shapely

from frasch.curationlist import Curation, LocalPoint, Square, Tuning
from frasch.dialect_areas import AreaIndex
from frasch.dialects import Dialect, Registry
from frasch.inject.claims import NameList
from frasch.inject.inputs import Inputs
from frasch.inject.report import input_lines, result_lines
from frasch.inject.stats import AddedPoint, AddedSquare, SkippedCarrier, Stats
from frasch.objects import point
from frasch.paths import Workspace
from frasch.placelist import PlaceRow
from frasch.refs import Ref
from conftest import REGISTRY

# the files of the run, by short paths
WS = replace(
    Workspace.at("/w"),
    names="places.csv",
    dialects="dialects.csv",
    areas="areas.geojson",
    curation="curation.csv",
    objects="osm_objects.json",
)
EXTRACT = "/maps/in.osm.pbf"

# inputs that hold nothing; a test replaces what it is about
EMPTY = Inputs(
    reg=REGISTRY,
    names=NameList({}, {}, 0),
    areas=AreaIndex([]),
    curation=Curation({}, {}, {}),
    objects={},
    local_places=[],
    members={},
    osm_local={},
)

HULM = PlaceRow({"mooring": "Hulm", "de": "Holm"}, 2)
NORDSIIE = PlaceRow({"mooring": "Nordsiie", "de": "Nordsee"}, 3)
BRAIST = PlaceRow({"mooring": "Bräist", "de": "Bredstedt"}, 4)
WAASTERHIAS = PlaceRow({"oomrang": "Waasterhias", "de": "Westerheide"}, 5)


def names(by_id: dict[Ref, PlaceRow], by_qid: dict[str, PlaceRow]) -> NameList:
    """The name list of the rows of `by_id` and `by_qid`."""
    return NameList(by_id, by_qid, len(by_id) + len(by_qid))


def curation(
    objects: dict[Ref, Tuning] | None = None,
    squares: dict[Ref, Square] | None = None,
    points: dict[Ref, LocalPoint] | None = None,
) -> Curation:
    """A curation of these parts, the others empty."""
    return Curation(objects or {}, squares or {}, points or {})


def local_point(label: str) -> LocalPoint:
    """A position for a local reference, from the curation row `label`."""
    return {"tags": {}, "label": label, "lon": 8.9, "lat": 54.6, "km2": None, "where": ""}


def line_starting(lines: list[str], start: str) -> str:
    """The one line of `lines` that starts with `start`."""
    (line,) = [line for line in lines if line.startswith(start)]
    return line


def optional_sections(stats: Stats, inputs: Inputs) -> list[list[str]]:
    """The sections of the result after the first, the objects tagged and
    the names written, which is always there; each section starts with an
    empty line."""
    sections: list[list[str]] = []
    for line in result_lines(stats, inputs, EXTRACT, 0):
        if line:
            sections[-1].append(line)
        else:
            sections.append([])
    return sections[1:]


# ------------------------------------------------------------- the inputs ---
def test_the_dialects_line_names_the_registrys_tags() -> None:
    reg = Registry(
        [
            Dialect(tag=f"frr-x-{column}", column=column, label="", status="", view="", note="")
            for column in ("mooring", "fering")
        ]
    )
    lines = input_lines(replace(EMPTY, reg=reg), WS)
    assert line_starting(lines, "dialects") == (
        "dialects  : dialects.csv -> 2 columns (frr-x-mooring, frr-x-fering)"
    )


def test_the_usable_line_counts_osm_ids_qids_and_local_references() -> None:
    by_id: dict[Ref, PlaceRow] = {
        ("n", 1): HULM,
        ("w", 2): BRAIST,
        ("l", "westerheide"): WAASTERHIAS,
    }
    lines = input_lines(replace(EMPTY, names=names(by_id, {"Q1693": NORDSIIE})), WS)
    assert line_starting(lines, "usable") == (
        "usable    : 4 rows -> 2 OSM ids + 1 wikidata QIDs + 1 local reference(s)"
    )


def test_the_usable_line_leaves_out_local_references_when_there_are_none() -> None:
    lines = input_lines(replace(EMPTY, names=names({("n", 1): HULM}, {})), WS)
    assert line_starting(lines, "usable") == "usable    : 1 rows -> 1 OSM ids + 0 wikidata QIDs"


def test_the_areas_line_counts_the_polygons_per_dialect() -> None:
    square = shapely.box(8.8, 54.5, 8.9, 54.6)
    areas = AreaIndex(
        [("frr-x-mooring", square), ("frr-x-hallig", square), ("frr-x-mooring", square)]
    )
    lines = input_lines(replace(EMPTY, areas=areas), WS)
    assert line_starting(lines, "areas") == (
        "areas     : areas.geojson -> 3 polygon(s): frr-x-hallig (1), frr-x-mooring (2)"
    )


def test_the_curation_line_counts_the_objects_and_their_zooms() -> None:
    objects: dict[Ref, Tuning] = {
        ("n", 1): {"tags": {"frasch:minzoom": "11"}, "label": "Holm"},
        ("n", 2): {"tags": {"frasch:minzoom": "10", "frasch:maxzoom": "14"}, "label": ""},
        ("r", 3): {"tags": {"place": "island"}, "label": ""},
    }
    lines = input_lines(replace(EMPTY, curation=curation(objects)), WS)
    assert line_starting(lines, "curation") == (
        "curation  : curation.csv -> 3 OSM ids (2 with frasch:minzoom, 1 with frasch:maxzoom)"
    )


def test_the_curation_line_is_there_without_osm_ids() -> None:
    lines = input_lines(EMPTY, WS)
    assert line_starting(lines, "curation") == (
        "curation  : curation.csv -> 0 OSM ids (0 with frasch:minzoom, 0 with frasch:maxzoom)"
    )


def test_the_synthetic_line_counts_the_squares_to_add() -> None:
    square: Square = {"tags": {}, "label": "", "km2": 50.0}
    squares: dict[Ref, Square] = {("n", 1): square, ("n", 2): square}
    lines = input_lines(replace(EMPTY, curation=curation(squares=squares)), WS)
    assert line_starting(lines, "synthetic") == "synthetic : 2 polygon(s) to add around nodes"


def test_the_local_line_counts_the_positioned_local_references() -> None:
    points: dict[Ref, LocalPoint] = {("l", "a"): local_point("A"), ("l", "b"): local_point("B")}
    lines = input_lines(replace(EMPTY, curation=curation(points=points)), WS)
    assert line_starting(lines, "local") == (
        "local     : 2 local reference(s) positioned in curation.csv"
    )


def test_a_position_no_row_uses_is_named() -> None:
    points: dict[Ref, LocalPoint] = {
        ("l", "used"): local_point("Used"),
        ("l", "nowhere"): local_point("Nowhere"),
    }
    inputs = replace(
        EMPTY,
        names=names({("l", "used"): WAASTERHIAS}, {}),
        curation=curation(points=points),
    )
    assert [line for line in input_lines(inputs, WS) if line.startswith("  !")] == [
        "  ! local/nowhere (Nowhere) is positioned in curation.csv but no row of places.csv "
        "uses it -- nothing added"
    ]


def test_the_objects_line_counts_the_located_objects() -> None:
    objects = {("n", 1): point(8.9, 54.6), ("w", 2): point(8.8, 54.7)}
    lines = input_lines(replace(EMPTY, objects=objects), WS)
    assert line_starting(lines, "objects") == "objects   : osm_objects.json -> 2 located object(s)"


def test_the_waterways_line_counts_the_member_ways() -> None:
    members = {("w", 10): (("r", 20), "Arlau"), ("w", 11): (("r", 20), "Arlau")}
    lines = input_lines(replace(EMPTY, members=members), WS)
    assert line_starting(lines, "waterways") == (
        "waterways : 2 member ways of matched waterway relations"
    )


def test_the_name_frr_line_counts_osms_frisian_names_no_row_holds() -> None:
    osm_local = {("n", 1): "Schörkeweerw", ("w", 2): "Jenswäärw"}
    lines = input_lines(replace(EMPTY, osm_local=osm_local), WS)
    assert line_starting(lines, "name:frr") == (
        "name:frr  : 2 object(s) in a dialect area that no row holds by reference have one in OSM"
    )


def test_empty_inputs_get_only_the_lines_of_the_files() -> None:
    assert [line[:10] for line in input_lines(EMPTY, WS)] == [
        "name list ",
        "dialects  ",
        "usable    ",
        "areas     ",
        "curation  ",
        "objects   ",
    ]


# --------------------------------------------- what was tagged and named ---
def test_the_scanned_line_gives_the_objects_and_the_seconds() -> None:
    lines = result_lines(Stats(scanned=12345), EMPTY, EXTRACT, 2.6)
    assert line_starting(lines, "scanned") == "scanned 12,345 objects in 3s"


def test_the_tagged_line_counts_the_objects_by_type() -> None:
    stats = Stats(tagged=collections.Counter(n=2, w=1, r=3))
    lines = result_lines(stats, EMPTY, EXTRACT, 0)
    assert line_starting(lines, "tagged") == "tagged  6 objects: 2 nodes, 1 ways, 3 relations"


def test_the_tagged_line_tells_the_qids_found_when_the_list_has_some() -> None:
    inputs = replace(EMPTY, names=names({}, {"Q1693": NORDSIIE, "Q559369": HULM}))
    stats = Stats(qid_carriers=1, present_qids={"Q1693"})
    assert line_starting(result_lines(stats, inputs, EXTRACT, 0), "tagged") == (
        "tagged  0 objects: 0 nodes, 0 ways, 0 relations "
        "(of these 1 matched by wikidata: 1 of 2 QIDs present)"
    )


def test_the_tagged_line_tells_the_member_ways_when_there_are_waterways() -> None:
    inputs = replace(EMPTY, members={("w", 10): (("r", 20), "Arlau")})
    stats = Stats(member_ways=1)
    assert line_starting(result_lines(stats, inputs, EXTRACT, 0), "tagged") == (
        "tagged  0 objects: 0 nodes, 0 ways, 0 relations; "
        "1 same-named member ways of waterway relations"
    )


def test_the_names_are_listed_per_dialect_in_registry_order_with_its_label() -> None:
    # name:de is no dialect's
    written = {"name:frr-x-oomrang": 1, "name:de": 4, "name:frr-x-mooring": 4}
    lines = result_lines(Stats(names=collections.Counter(written)), EMPTY, EXTRACT, 0)
    assert [line for line in lines if line.startswith("  name:")] == [
        "  name:frr-x-mooring       4  Mooring",
        "  name:frr-x-oomrang       1  Öömrang",
    ]


def test_the_local_forms_line_says_how_many_are_osms_frisian_name() -> None:
    lines = result_lines(Stats(local=3, osm_local_claimed=1), EMPTY, EXTRACT, 0)
    assert [line for line in lines if line.startswith("  frasch:local")] == [
        "  frasch:local             3  local form (1 of them OSM's name:frr)"
    ]


def test_osms_frisian_names_on_objects_no_row_claims_get_a_line_of_their_own() -> None:
    lines = result_lines(Stats(osm_local_unclaimed=2), EMPTY, EXTRACT, 0)
    assert [line for line in lines if line.startswith("  frasch:local")] == [
        "  frasch:local             0  local form",
        "  frasch:local             2  OSM's name:frr on objects no row claims",
    ]


def area_lines(stats: Stats) -> list[str]:
    """The lines under "objects per dialect area:", the last of the first
    section, in a result of nothing more than `stats`."""
    lines = result_lines(stats, EMPTY, EXTRACT, 0)
    return lines[lines.index("objects per dialect area:") + 1 :]


def test_the_objects_per_dialect_area_are_listed_most_first() -> None:
    stats = Stats(dialects=collections.Counter({"frr-x-hallig": 1, "frr-x-mooring": 3}))
    assert area_lines(stats) == [
        "  frasch:dialect=frr-x-mooring       3",
        "  frasch:dialect=frr-x-hallig        1",
    ]


def test_no_object_in_a_dialect_area_is_said_so() -> None:
    assert area_lines(Stats()) == ["  (none -- no tagged object lies in a dialect area)"]


def test_a_run_that_did_nothing_has_no_more_sections() -> None:
    assert optional_sections(Stats(), EMPTY) == []


# ------------------------------------------- what was added and not found ---
def test_an_added_node_is_listed_with_its_row_position_and_tags_but_names() -> None:
    key = ("l", "westerheide-amrum")
    tags = {"place": "hamlet", "name": "Westerheide", "name:de": "Westerheide", "frasch:local": "W"}
    stats = Stats(added_points=[AddedPoint(7, key, 8.34019, 54.65097, tags)])
    inputs = replace(EMPTY, names=names({key: WAASTERHIAS}, {}))
    assert optional_sections(stats, inputs) == [
        [
            "added 1 node(s) for places that are not in OSM:",
            "  node/7  local/westerheide-amrum Waasterhias (Westerheide) at 54.65097, 8.34019: "
            "frasch:local=W, place=hamlet",
        ]
    ]


def test_the_rows_whose_objects_the_extract_lacks_are_listed() -> None:
    # a local reference is not looked for in the extract
    by_id: dict[Ref, PlaceRow] = {
        ("n", 1): HULM,
        ("n", 99): BRAIST,
        ("l", "westerheide"): WAASTERHIAS,
    }
    stats = Stats(found={("n", 1)})
    assert optional_sections(stats, replace(EMPTY, names=names(by_id, {}))) == [
        ["1 rows reference ids that are not in in.osm.pbf:", "  node/99  Bräist"]
    ]


def test_the_qids_no_object_carries_are_listed() -> None:
    inputs = replace(EMPTY, names=names({}, {"Q1693": NORDSIIE, "Q559369": HULM}))
    stats = Stats(present_qids={"Q559369"})
    assert optional_sections(stats, inputs) == [
        ["1 wikidata QIDs not present in the file: Q1693 (Nordsiie)"]
    ]


def test_the_qid_carriers_left_alone_are_listed() -> None:
    inputs = replace(EMPTY, names=names({}, {"Q559369": HULM}))
    stats = Stats(
        present_qids={"Q559369"},
        skipped_carriers=[SkippedCarrier(("n", 6), "Rosen-Huus", "Q559369")],
    )
    assert optional_sections(stats, inputs) == [
        [
            "1 objects carry a QID of the list but are not place-like -- not tagged:",
            "  node/6  Rosen-Huus: Q559369 (Hulm)",
        ]
    ]


# --------------------------------------------------------- the curation ---
def test_the_curated_objects_are_listed_by_type_with_their_tags() -> None:
    objects: dict[Ref, Tuning] = {
        ("r", 5): {"tags": {"place": "island", "frasch:minzoom": "12"}, "label": "Hallig"},
        ("n", 2): {"tags": {"frasch:minzoom": "10"}, "label": "Tammensiel"},
        ("n", 1): {"tags": {"frasch:minzoom": "11"}, "label": "Holm"},
    }
    stats = Stats(curated={("n", 1), ("n", 2), ("r", 5)})
    assert optional_sections(stats, replace(EMPTY, curation=curation(objects))) == [
        [
            "curated 3 objects: 2 nodes, 0 ways, 1 relations",
            "  node/1  Holm: frasch:minzoom=11",
            "  node/2  Tammensiel: frasch:minzoom=10",
            "  relation/5  Hallig: frasch:minzoom=12, place=island",
        ]
    ]


def test_the_curation_rows_whose_objects_the_extract_lacks_are_listed() -> None:
    objects: dict[Ref, Tuning] = {
        ("n", 1): {"tags": {"frasch:minzoom": "11"}, "label": "Holm"},
        ("n", 98): {"tags": {"frasch:minzoom": "10"}, "label": "Gone"},
    }
    stats = Stats(curated={("n", 1)})
    sections = optional_sections(stats, replace(EMPTY, curation=curation(objects)))
    assert sections[-1] == [
        "1 curation rows reference ids that are not in in.osm.pbf:",
        "  node/98  Gone",
    ]


def test_an_added_synthetic_polygon_is_listed_with_its_nodes_and_area() -> None:
    square = AddedSquare(12, [7, 8, 9, 10], ("l", "sophien-koog"), "Sophien-Koog", 2.0)
    assert optional_sections(Stats(added_squares=[square]), EMPTY) == [
        ["added 1 synthetic polygon(s):", "  way/12 (node/7..node/10)  Sophien-Koog: 2 km²"]
    ]


def test_a_synthetic_polygon_whose_node_the_extract_lacks_is_named() -> None:
    squares: dict[Ref, Square] = {
        ("n", 97): {"tags": {"place": "island"}, "label": "Gone island", "km2": 5.0}
    }
    assert optional_sections(Stats(), replace(EMPTY, curation=curation(squares=squares))) == [
        [
            "added 0 synthetic polygon(s):",
            "  ! node/97 Gone island: node not in in.osm.pbf, no polygon added",
        ]
    ]
