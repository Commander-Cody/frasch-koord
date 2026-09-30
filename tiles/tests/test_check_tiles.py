"""check_tiles.compare: what counts as the map and the search index
disagreeing."""
from __future__ import annotations

from frasch import check_tiles
from frasch.check_tiles import Label
from frasch.searchindex import SearchEntry


def entry(ident: str, osm: str, lon: float, lat: float) -> SearchEntry:
    """A search entry with the fields the check does not read left empty."""
    return {"id": ident, "names": {}, "name_de": "", "lon": lon, "lat": lat,
            "kind": "settlement", "osm": osm}


STIARDEBEL = entry("stiardebel", "node/1; way/2", 9.25, 54.5) | {
    "dialect": "frr-x-suedgoes", "local": "Stiardebel"}


def feature(osm: str | None, lon: float | None = None, lat: float | None = None,
            **props: str) -> Label:
    props = {k.replace("_", ":"): v for k, v in props.items()}
    f: Label = {"osm": osm, "props": {"frasch:ref": "stiardebel", **props}}
    if lon is not None and lat is not None:
        f |= {"lon": lon, "lat": lat}
    return f


AGREEING = feature("node/1", 9.25, 54.5, frasch_dialect="frr-x-suedgoes",
                   frasch_local="Stiardebel")


def test_a_feature_that_says_what_its_entry_says_passes() -> None:
    assert check_tiles.compare({"stiardebel": STIARDEBEL}, [AGREEING]) == []


def test_another_dialect_on_the_map_is_reported() -> None:
    wrong = AGREEING | {"props": AGREEING["props"] | {"frasch:dialect": "frr-x-nordgoes",
                                                      "frasch:local": "Steerdebel"}}
    problems = check_tiles.compare({"stiardebel": STIARDEBEL}, [wrong])
    assert len(problems) == 2
    assert "frr-x-nordgoes" in problems[0] and "Steerdebel" in problems[1]


def test_a_label_somewhere_else_is_reported() -> None:
    moved = AGREEING | {"lon": 9.26}
    assert len(check_tiles.compare({"stiardebel": STIARDEBEL}, [moved])) == 1


def test_the_rows_other_objects_may_lie_in_another_area() -> None:
    second = feature("way/2", frasch_dialect="frr-x-nordgoes")
    assert check_tiles.compare({"stiardebel": STIARDEBEL}, [second]) == []


def test_a_place_osm_does_not_have_is_compared_on_its_added_node() -> None:
    local = STIARDEBEL | {"osm": "local/stiardebel"}
    added = feature(None, 9.25, 54.5, frasch_dialect="frr-x-nordgoes",
                    frasch_local="Stiardebel")
    assert len(check_tiles.compare({"stiardebel": local}, [added])) == 1


def test_a_polygons_label_point_is_planetilers_own() -> None:
    # Pellworm: a way whose label Planetiler places itself, a few metres off
    pellworm = entry("pelweerm", "way/1472528448", 8.64127, 54.52347)
    label: Label = {"osm": "way/1472528448", "props": {"frasch:ref": "pelweerm"},
                      "lon": 8.64149, "lat": 54.52356}
    assert check_tiles.compare({"pelweerm": pellworm}, [label]) == []


def test_only_entries_whose_own_object_is_labelled_count_as_checked() -> None:
    # Stiardebel's second object is labelled, its own is not; Pellworm's is
    pellworm = entry("pelweerm", "way/1472528448", 8.64, 54.52)
    features: list[Label] = [feature("way/2"),
                               {"osm": "way/1472528448", "props": {"frasch:ref": "pelweerm"}}]
    entries = {"stiardebel": STIARDEBEL, "pelweerm": pellworm}
    assert check_tiles.checked_entries(entries, features) == {"pelweerm"}
