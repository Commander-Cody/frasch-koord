"""`frasch check-tiles`: what counts as the map and the search index
disagreeing (check_tiles.compare), and the command on a tile archive."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import mapbox_vector_tile
import pytest
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

from frasch import check_tiles
from frasch.__main__ import main
from frasch.check_tiles import Label
from frasch.placenames import SearchEntry
from conftest import REGISTRY, REGISTRY_CSV


def entry(ident: str, osm: str, lon: float, lat: float) -> SearchEntry:
    """A search entry with the fields the check does not read left empty."""
    return {
        "id": ident,
        "names": {},
        "name_de": "",
        "lon": lon,
        "lat": lat,
        "kind": "settlement",
        "osm": osm,
    }


STIARDEBEL = entry("stiardebel", "node/1; way/2", 9.25, 54.5) | {
    "names": {"frr-x-mooring": "Stiirdebel"},
    "dialect": "frr-x-suedgoes",
    "local": "Stiardebel",
}


def feature(
    osm: str | None,
    lon: float | None = None,
    lat: float | None = None,
    ref: str = "stiardebel",
    **props: str,
) -> Label:
    """A labelled feature of the row `ref`, a settlement like every `entry`."""
    props = {k.replace("_", ":"): v for k, v in props.items()}
    f: Label = {"osm": osm, "props": {"frasch:ref": ref, "frasch:kind": "settlement", **props}}
    if lon is not None and lat is not None:
        f |= {"lon": lon, "lat": lat}
    return f


def with_props(label: Label, **props: str) -> Label:
    return label | {"props": label["props"] | {k.replace("_", ":"): v for k, v in props.items()}}


AGREEING = feature(
    "node/1",
    9.25,
    54.5,
    **{"name:frr-x-mooring": "Stiirdebel"},
    frasch_dialect="frr-x-suedgoes",
    frasch_local="Stiardebel",
)


def compare(entry: SearchEntry, *features: Label) -> list[str]:
    return check_tiles.compare({entry["id"]: entry}, features, REGISTRY)


def test_a_feature_that_says_what_its_entry_says_passes() -> None:
    assert compare(STIARDEBEL, AGREEING) == []


def test_another_kind_on_the_map_is_reported() -> None:
    (problem,) = compare(STIARDEBEL, with_props(AGREEING, frasch_kind="warft"))
    assert "'warft'" in problem and "'settlement'" in problem


def test_a_dialect_name_missing_from_the_map_is_reported() -> None:
    unnamed = AGREEING | {"props": {k: v for k, v in AGREEING["props"].items() if k[:5] != "name:"}}
    (problem,) = compare(STIARDEBEL, unnamed)
    assert "name:frr-x-mooring=None" in problem and "'Stiirdebel'" in problem


def test_a_dialect_name_only_the_map_has_is_reported() -> None:
    # tiles built from another state of the list: its row has no such name now
    merged = with_props(AGREEING, **{"name:frr-x-wieding": "Stäirdebel"})
    (problem,) = compare(STIARDEBEL, merged)
    assert "'Stäirdebel'" in problem and "names[frr-x-wieding]=None" in problem


def test_another_variety_on_the_map_is_reported() -> None:
    (problem,) = compare(STIARDEBEL, with_props(AGREEING, frasch_variety="Foortuftinge"))
    assert "'Foortuftinge'" in problem


def test_another_dialect_on_the_map_is_reported() -> None:
    wrong = with_props(AGREEING, frasch_dialect="frr-x-nordgoes", frasch_local="Steerdebel")
    problems = compare(STIARDEBEL, wrong)
    assert len(problems) == 2
    assert "frr-x-nordgoes" in problems[0] and "Steerdebel" in problems[1]


def test_another_german_name_on_the_map_is_reported() -> None:
    # the card's German step reads the list's `de`, the label OSM's (#61)
    listed = STIARDEBEL | {"name_de": "Stadum"}
    osms = with_props(AGREEING, **{"name:de": "Stadum (Nordfriesland)"})
    (problem,) = compare(listed, osms)
    assert "Stadum (Nordfriesland)" in problem and "'Stadum'" in problem


def test_osms_german_name_may_stand_where_the_list_has_none() -> None:
    osms = with_props(AGREEING, **{"name:de": "Stadum"})
    assert compare(STIARDEBEL, osms) == []


def test_a_label_somewhere_else_is_reported() -> None:
    moved = AGREEING | {"lon": 9.26}
    assert len(compare(STIARDEBEL, moved)) == 1


def test_the_rows_other_objects_may_lie_in_another_area() -> None:
    second = feature("way/2", frasch_dialect="frr-x-nordgoes")
    assert compare(STIARDEBEL, second) == []


def test_a_place_osm_does_not_have_is_compared_on_its_added_node() -> None:
    local = STIARDEBEL | {"osm": "local/stiardebel"}
    added = with_props(AGREEING | {"osm": None}, frasch_dialect="frr-x-nordgoes")
    assert len(compare(local, added)) == 1


def test_a_polygons_label_point_is_planetilers_own() -> None:
    # Pellworm: a way whose label Planetiler places itself, a few metres off
    pellworm = entry("pelweerm", "way/1472528448", 8.64127, 54.52347)
    label = feature("way/1472528448", 8.64149, 54.52356, ref="pelweerm")
    assert compare(pellworm, label) == []


# Stiardebel as if its row's object were a relation with a curation square:
# the square's label has the id of the way the injector made up
SQUARED = STIARDEBEL | {"osm": "relation/3"}
SQUARE = with_props(AGREEING | {"osm": "way/1561415191"}, frasch_square="yes")


def test_a_squares_label_is_compared_with_the_entry_of_its_row() -> None:
    (problem,) = compare(SQUARED, with_props(SQUARE, frasch_kind="warft"))
    assert "'warft'" in problem


def test_a_squares_label_somewhere_else_is_reported() -> None:
    assert len(compare(SQUARED, SQUARE | {"lon": 9.26})) == 1


def test_an_entry_whose_square_is_labelled_counts_as_checked() -> None:
    assert check_tiles.checked_entries({"stiardebel": SQUARED}, [SQUARE]) == {"stiardebel"}


def test_only_entries_whose_own_object_is_labelled_count_as_checked() -> None:
    # Stiardebel's second object is labelled, its own is not; Pellworm's is
    pellworm = entry("pelweerm", "way/1472528448", 8.64, 54.52)
    features = [feature("way/2"), feature("way/1472528448", ref="pelweerm")]
    entries = {"stiardebel": STIARDEBEL, "pelweerm": pellworm}
    assert check_tiles.checked_entries(entries, features) == {"pelweerm"}


# ------------------------------------------------------ reading the tiles ---
@pytest.mark.parametrize("feature_id, ref", [(11, "node/1"), (22, "way/2"), (1233, "relation/123")])
def test_a_feature_id_is_the_osm_id_times_ten_plus_the_type(feature_id: int, ref: str) -> None:
    assert check_tiles.osm_ref(feature_id) == ref


@pytest.mark.parametrize("feature_id", [None, 0, -11, 14])
def test_a_feature_id_no_osm_object_has_is_none(feature_id: int | None) -> None:
    assert check_tiles.osm_ref(feature_id) is None


def test_a_point_lies_in_the_tile_of_its_quadrant() -> None:
    # at zoom 1 the world is four tiles, numbered from the north-west
    assert check_tiles.tile_of(90, -45, 1) == (1, 1)


def test_a_tiles_north_west_corner_is_where_web_mercator_ends() -> None:
    lon, lat = check_tiles.lonlat(1, 0, 0, 0, 0, 4096)
    assert (lon, lat) == pytest.approx((-180, 85.0511288))


def test_the_middle_of_a_tile_lies_in_that_tile() -> None:
    assert check_tiles.tile_of(*check_tiles.lonlat(14, 8669, 5300, 2048, 2048, 4096), 14) == (
        8669,
        5300,
    )


def encoded_tile(*features: dict[str, object]) -> bytes:
    """A gzip-compressed vector tile of one layer, as an archive holds it;
    point coordinates in tile units, y pointing down."""
    tile = mapbox_vector_tile.encode(
        [{"name": "place", "features": list(features)}], default_options={"y_coord_down": True}
    )
    return gzip.compress(tile)


def test_a_tile_yields_its_labelled_features_with_their_object_and_position() -> None:
    # the south-west corner of zoom 1's north-east tile: lon 0, lat 0
    data = encoded_tile(
        {
            "id": 11,
            "geometry": {"type": "Point", "coordinates": [0, 4096]},
            "properties": {"frasch:ref": "stiardebel", "name": "Stadum"},
        }
    )

    (label,) = check_tiles.tile_features(data, 1, 1, 0)

    assert label == {
        "osm": "node/1",
        "props": {"frasch:ref": "stiardebel", "name": "Stadum"},
        "lon": pytest.approx(0),
        "lat": pytest.approx(0),
    }


def test_a_labelled_shape_has_no_position() -> None:
    data = encoded_tile(
        {
            "id": 22,
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 10]]},
            "properties": {"frasch:ref": "nordwarw"},
        }
    )

    assert check_tiles.tile_features(data, 1, 1, 0) == [
        {"osm": "way/2", "props": {"frasch:ref": "nordwarw"}}
    ]


def test_a_tiles_features_without_a_row_are_left_out() -> None:
    data = encoded_tile(
        {
            "id": 31,
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"name": "Kiel"},
        }
    )

    assert check_tiles.tile_features(data, 1, 1, 0) == []


# ---------------------------------------------------------- the command ---
def write_archive(path: Path, entry: SearchEntry, **props: check_tiles.PropValue) -> Path:
    """A PMTiles archive of one z14 tile: the tile `entry` lies in, holding
    the label of node/1 at the tile's corner, with the properties `props`."""
    x, y = check_tiles.tile_of(entry["lon"], entry["lat"], 14)
    label = {
        "id": 11,  # OpenMapTiles' id of node/1
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "properties": props,
    }
    tile = mapbox_vector_tile.encode([{"name": "place", "features": [label]}])
    with open(path, "wb") as fh:
        writer = Writer(fh)
        writer.write_tile(zxy_to_tileid(14, x, y), gzip.compress(tile))
        writer.finalize(
            {
                "tile_type": TileType.MVT,
                "tile_compression": Compression.GZIP,
                "min_zoom": 14,
                "max_zoom": 14,
                "min_lon_e7": int(-180e7),
                "min_lat_e7": int(-85e7),
                "max_lon_e7": int(180e7),
                "max_lat_e7": int(85e7),
                "center_zoom": 14,
                "center_lon_e7": 0,
                "center_lat_e7": 0,
            },
            {},
        )
    return path


def test_the_command_fails_on_an_archive_that_disagrees_with_the_index_its_option_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    index = tmp_path / "names.json"
    index.write_text(json.dumps({"places": [STIARDEBEL]}), encoding="utf-8")
    dialects = tmp_path / "dialects.csv"
    dialects.write_text(REGISTRY_CSV, encoding="utf-8")
    # the label says what the entry says, but lies at the corner of its tile
    archive = write_archive(tmp_path / "tiles.pmtiles", STIARDEBEL, **AGREEING["props"])
    files = ["--index", str(index), "--dialects", str(dialects)]
    assert main(["check-tiles", str(archive), *files]) == 1
    assert capsys.readouterr().err == f"1 disagreement(s) between {archive} and {index}\n"
