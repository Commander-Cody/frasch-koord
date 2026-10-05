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
from frasch.searchindex import SearchEntry


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
    "dialect": "frr-x-suedgoes",
    "local": "Stiardebel",
}


def feature(
    osm: str | None, lon: float | None = None, lat: float | None = None, **props: str
) -> Label:
    props = {k.replace("_", ":"): v for k, v in props.items()}
    f: Label = {"osm": osm, "props": {"frasch:ref": "stiardebel", **props}}
    if lon is not None and lat is not None:
        f |= {"lon": lon, "lat": lat}
    return f


AGREEING = feature("node/1", 9.25, 54.5, frasch_dialect="frr-x-suedgoes", frasch_local="Stiardebel")


def test_a_feature_that_says_what_its_entry_says_passes() -> None:
    assert check_tiles.compare({"stiardebel": STIARDEBEL}, [AGREEING]) == []


def test_another_dialect_on_the_map_is_reported() -> None:
    wrong = AGREEING | {
        "props": AGREEING["props"]
        | {"frasch:dialect": "frr-x-nordgoes", "frasch:local": "Steerdebel"}
    }
    problems = check_tiles.compare({"stiardebel": STIARDEBEL}, [wrong])
    assert len(problems) == 2
    assert "frr-x-nordgoes" in problems[0] and "Steerdebel" in problems[1]


def test_another_german_name_on_the_map_is_reported() -> None:
    # the card's German step reads the list's `de`, the label OSM's (#61)
    listed = STIARDEBEL | {"name_de": "Stadum"}
    osms = AGREEING | {"props": AGREEING["props"] | {"name:de": "Stadum (Nordfriesland)"}}
    (problem,) = check_tiles.compare({"stiardebel": listed}, [osms])
    assert "Stadum (Nordfriesland)" in problem and "'Stadum'" in problem


def test_osms_german_name_may_stand_where_the_list_has_none() -> None:
    osms = AGREEING | {"props": AGREEING["props"] | {"name:de": "Stadum"}}
    assert check_tiles.compare({"stiardebel": STIARDEBEL}, [osms]) == []


def test_a_label_somewhere_else_is_reported() -> None:
    moved = AGREEING | {"lon": 9.26}
    assert len(check_tiles.compare({"stiardebel": STIARDEBEL}, [moved])) == 1


def test_the_rows_other_objects_may_lie_in_another_area() -> None:
    second = feature("way/2", frasch_dialect="frr-x-nordgoes")
    assert check_tiles.compare({"stiardebel": STIARDEBEL}, [second]) == []


def test_a_place_osm_does_not_have_is_compared_on_its_added_node() -> None:
    local = STIARDEBEL | {"osm": "local/stiardebel"}
    added = feature(None, 9.25, 54.5, frasch_dialect="frr-x-nordgoes", frasch_local="Stiardebel")
    assert len(check_tiles.compare({"stiardebel": local}, [added])) == 1


def test_a_polygons_label_point_is_planetilers_own() -> None:
    # Pellworm: a way whose label Planetiler places itself, a few metres off
    pellworm = entry("pelweerm", "way/1472528448", 8.64127, 54.52347)
    label: Label = {
        "osm": "way/1472528448",
        "props": {"frasch:ref": "pelweerm"},
        "lon": 8.64149,
        "lat": 54.52356,
    }
    assert check_tiles.compare({"pelweerm": pellworm}, [label]) == []


def test_only_entries_whose_own_object_is_labelled_count_as_checked() -> None:
    # Stiardebel's second object is labelled, its own is not; Pellworm's is
    pellworm = entry("pelweerm", "way/1472528448", 8.64, 54.52)
    features: list[Label] = [
        feature("way/2"),
        {"osm": "way/1472528448", "props": {"frasch:ref": "pelweerm"}},
    ]
    entries = {"stiardebel": STIARDEBEL, "pelweerm": pellworm}
    assert check_tiles.checked_entries(entries, features) == {"pelweerm"}


# ---------------------------------------------------------- the command ---
def write_archive(path: Path, entry: SearchEntry, **props: str) -> Path:
    """A PMTiles archive of one z14 tile: the tile `entry` lies in, holding
    the label of node/1 for its row at the tile's corner, with the properties
    `props`."""
    x, y = check_tiles.tile_of(entry["lon"], entry["lat"], 14)
    label = {
        "id": 11,  # OpenMapTiles' id of node/1
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "properties": {"frasch:ref": entry["id"], **props},
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
    # the label says what the entry says, but lies at the corner of its tile
    agreeing = {"frasch:dialect": "frr-x-suedgoes", "frasch:local": "Stiardebel"}
    archive = write_archive(tmp_path / "tiles.pmtiles", STIARDEBEL, **agreeing)
    assert main(["check-tiles", str(archive), "--index", str(index)]) == 1
    assert capsys.readouterr().err == f"1 disagreement(s) between {archive} and {index}\n"
