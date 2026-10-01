"""curationlist.py: the one reader of names/curation.csv -- per-object map
tuning, the synthetic squares and the positions of the places OSM does not
have (names/README.md, "Map curation")."""
from __future__ import annotations

from pathlib import Path

import pytest

from frasch import curationlist
from frasch.errors import ValidationError
from conftest import curation_file


# --------------------------------------------------------------- the file ---
def test_curation_row_tags_an_osm_object(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "way/177387348", "name": "Habel",
                                    "set_tags": "place=island"})
    by_id, synthetic, points = curationlist.read(path)
    assert by_id == {("w", 177387348): {"tags": {"place": "island"}, "label": "Habel"}}
    assert synthetic == {} and points == {}


def test_curation_zooms_become_string_tags(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "node/355956234", "name": "Tammensiel",
                                    "minzoom": "10", "maxzoom": "12"})
    by_id, _, _ = curationlist.read(path)
    assert by_id[("n", 355956234)]["tags"] == {"frasch:minzoom": "10",
                                               "frasch:maxzoom": "12"}


def test_curation_row_with_several_objects_tags_each(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "way/44051131; way/44051132",
                                    "name": "Arlau",
                                    "set_tags": "name:frr-x-mooring=Arlou"})
    by_id, _, _ = curationlist.read(path)
    assert set(by_id) == {("w", 44051131), ("w", 44051132)}
    assert by_id[("w", 44051132)]["tags"] == {"name:frr-x-mooring": "Arlou"}


def test_curation_row_with_nothing_to_apply_is_skipped(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "node/1", "name": "just a note",
                                    "note": "look at this later"})
    assert curationlist.read(path) == ({}, {}, {})


def test_polygon_km2_row_describes_a_square_not_a_tag_change(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "node/85929111", "name": "Nordstrand",
                                    "set_tags": "place=island", "maxzoom": "11",
                                    "polygon_km2": "50"})
    by_id, synthetic, _ = curationlist.read(path)
    assert by_id == {}
    assert synthetic == {("n", 85929111): {
        "km2": 50.0, "tags": {"place": "island", "frasch:maxzoom": "11"},
        "label": "Nordstrand"}}


def test_local_reference_row_positions_a_place(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "local/westerheide-amrum",
                                    "name": "Westerheide (Amrum)",
                                    "lat": "54.65097", "lon": "8.34019"})
    _, _, points = curationlist.read(path)
    p = points[("l", "westerheide-amrum")]
    assert (p["lon"], p["lat"], p["km2"], p["tags"]) == (8.34019, 54.65097, None, {})


@pytest.mark.parametrize("bad,message", [
    ({"osm": "node/85929111", "lat": "54.48", "lon": "8.86"}, "only go with a local"),
    ({"osm": "local/westerheide-amrum"}, "needs `lat` and `lon`"),
    ({"osm": "node/355956234", "minzoom": "ten"}, "not an integer"),
    ({"osm": "node/355956234", "minzoom": "--5"}, "not an integer"),
    ({"osm": "node/355956234", "minzoom": "-5"}, r"minzoom '-5' is not a zoom \(0-24\)"),
    ({"osm": "node/355956234", "maxzoom": "99"}, r"maxzoom '99' is not a zoom \(0-24\)"),
    ({"osm": "node/355956234", "minzoom": "12", "maxzoom": "10"},
     "maxzoom 10 is below minzoom 12"),
    ({"osm": "node/85929111", "polygon_km2": "0"}, "not a positive number"),
    ({"osm": "node/85929111", "polygon_km2": "fifty"}, "not a positive number"),
    ({"osm": "node/85929111", "polygon_km2": "inf"}, "not a positive number"),
    ({"osm": "way/177387348", "polygon_km2": "5"}, "exactly one node"),
    ({"osm": "node/1; node/2", "polygon_km2": "5"}, "exactly one node"),
])
def test_bad_curation_row_stops_the_build(tmp_path: Path, bad: dict[str, str],
                                          message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        curationlist.read(curation_file(tmp_path, bad))


def test_second_row_for_one_local_reference_stops_the_build(tmp_path: Path) -> None:
    row = {"osm": "local/huelltoft", "lat": "54.881287", "lon": "8.771304"}
    with pytest.raises(ValidationError, match="second row"):
        curationlist.read(curation_file(tmp_path, row, row))


def test_second_polygon_for_one_node_stops_the_build(tmp_path: Path) -> None:
    row = {"osm": "node/85929111", "polygon_km2": "50"}
    with pytest.raises(ValidationError, match="second polygon_km2"):
        curationlist.read(curation_file(tmp_path, row, row))


@pytest.mark.parametrize("first", ["way/44051131", "way/44051130; way/44051131"])
def test_second_row_for_one_osm_object_stops_the_build(tmp_path: Path, first: str) -> None:
    path = curation_file(tmp_path, {"osm": first, "set_tags": "waterway=river"},
                         {"osm": "way/44051131", "maxzoom": "12"})
    with pytest.raises(ValidationError) as exc:
        curationlist.read(path)
    assert exc.value.problems == [f"{path}:3: second row for way/44051131 (line 2)"]


def test_a_node_with_a_square_may_have_a_row_of_its_own(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "node/85929111", "polygon_km2": "50"},
                         {"osm": "node/85929111", "minzoom": "12"})
    by_id, synthetic, _ = curationlist.read(path)
    assert by_id[("n", 85929111)]["tags"] == {"frasch:minzoom": "12"}
    assert set(synthetic) == {("n", 85929111)}


def test_every_broken_row_is_reported_at_once(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "node/1", "minzoom": "ten"},
                         {"osm": "node/2", "name": "fine", "minzoom": "10"},
                         {"osm": "local/nowhere"})
    with pytest.raises(ValidationError) as exc:
        curationlist.read(path)
    assert exc.value.problems == [f"{path}:2: minzoom 'ten' is not an integer",
                                  f"{path}:4: local/nowhere needs `lat` and `lon`"]


def test_the_local_points_are_the_positions_of_the_local_references(tmp_path: Path) -> None:
    path = curation_file(tmp_path, {"osm": "local/westerheide-amrum",
                                    "lat": "54.65097", "lon": "8.34019"},
                         {"osm": "node/1", "set_tags": "place=island"})
    assert curationlist.local_points(path) == {"westerheide-amrum": (8.34019, 54.65097)}


# ------------------------------------------------------------- parse_point ---
def test_parse_point_returns_lon_then_lat() -> None:
    # arguments are (lat, lon) like the curation columns, the result is
    # (lon, lat) like GeoJSON and shapely
    assert curationlist.parse_point("54.65097", "8.34019") == (8.34019, 54.65097)


def test_parse_point_ignores_surrounding_blanks() -> None:
    assert curationlist.parse_point(" 54.881287 ", "8.771304 ") == (8.771304, 54.881287)


def test_parse_point_of_two_empty_cells_is_no_point() -> None:
    assert curationlist.parse_point("", "") is None
    assert curationlist.parse_point(None, None) is None


@pytest.mark.parametrize("lat,lon", [("54.65097", ""), ("", "8.34019")])
def test_parse_point_needs_both_cells(lat: str, lon: str) -> None:
    with pytest.raises(ValidationError, match="go together"):
        curationlist.parse_point(lat, lon, "curation.csv:15")


@pytest.mark.parametrize("lat,lon", [
    ("54,65097", "8,34019"),          # a German spreadsheet's decimal comma
    ("54°39'N", "8°20'E"),
])
def test_parse_point_needs_decimal_degrees(lat: str, lon: str) -> None:
    with pytest.raises(ValidationError, match="not numbers"):
        curationlist.parse_point(lat, lon)


@pytest.mark.parametrize("lat,lon", [("91", "8.3"), ("-90.5", "8.3"), ("54.6", "181"),
                                     ("54.6", "-180.01")])
def test_parse_point_refuses_coordinates_off_the_globe(lat: str, lon: str) -> None:
    with pytest.raises(ValidationError, match="out of range"):
        curationlist.parse_point(lat, lon)


def test_parse_point_accepts_the_edges_of_the_globe() -> None:
    assert curationlist.parse_point("-90", "180") == (180.0, -90.0)


# ------------------------------------------------------------ parse_set_tags ---
def test_set_tags_are_k_equals_v_pairs() -> None:
    assert curationlist.parse_set_tags("place=island;frasch:kind=island") == {
        "place": "island", "frasch:kind": "island"}


def test_set_tags_ignore_blanks_and_empty_pairs() -> None:
    assert curationlist.parse_set_tags(" place = island ;; ") == {"place": "island"}


def test_set_tags_value_may_contain_an_equals_sign() -> None:
    assert curationlist.parse_set_tags("note=a=b") == {"note": "a=b"}


def test_set_tags_value_may_be_empty() -> None:
    assert curationlist.parse_set_tags("name:de=") == {"name:de": ""}


def test_empty_set_tags_are_no_tags() -> None:
    assert curationlist.parse_set_tags("") == {}
    assert curationlist.parse_set_tags(None) == {}


def test_set_tags_entry_without_equals_is_refused() -> None:
    with pytest.raises(ValidationError, match="not key=value"):
        curationlist.parse_set_tags("place=island;islet")


def test_set_tags_entry_with_empty_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="empty key"):
        curationlist.parse_set_tags("=island")
