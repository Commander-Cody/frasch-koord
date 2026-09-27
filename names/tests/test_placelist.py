"""placelist.py: the cell conventions of places.csv (README "Conventions that
apply to every name cell", the `osm` column, curation positions) and a
read/write round trip of the real name list.

Malformed name cells (unbalanced brackets, `?`, `;` without a space) are
deliberately not pinned down here: names/check.py owns them."""
from __future__ import annotations

import shutil

import pytest

import placelist


# ------------------------------------------------------------- name cells ---
def test_parts_splits_variants_and_keeps_each_remark():
    assert placelist.parts("Rübel; Rübbel (wisinge)") == [
        ("Rübel", ""), ("Rübbel", "wisinge")]


def test_semicolon_inside_a_remark_does_not_split():
    # the README's own example: two names, the remark lists two varieties
    assert placelist.parts("Huađer; Huuger (Sölring; Wisinge)") == [
        ("Huađer", ""), ("Huuger", "Sölring; Wisinge")]


def test_several_remarks_on_one_variant_are_joined():
    assert placelist.parts("Brouersweerw (Foortuftinge) (Nickelsen 1982)") == [
        ("Brouersweerw", "Foortuftinge; Nickelsen 1982")]


def test_empty_and_missing_cells_have_no_parts():
    assert placelist.parts("") == []
    assert placelist.parts(None) == []


def test_variants_strip_the_remarks():
    assert placelist.variants("Huađer; Huuger (Sölring; Wisinge)") == ["Huađer", "Huuger"]


def test_variants_list_a_name_once():
    # the same spelling with and without a source remark is one name
    assert placelist.variants("Hulm; Hulm (Wisinge)") == ["Hulm"]


def test_primary_is_the_first_variant_without_its_remark():
    assert placelist.primary("Lätj-Jäns-Weerw (Foortuftinge); Latj-Jäns-Wärw") == "Lätj-Jäns-Weerw"


def test_primary_of_an_empty_cell_is_empty():
    assert placelist.primary("") == ""
    assert placelist.primary(None) == ""


def test_remark_is_that_of_the_primary_variant():
    assert placelist.remark("Brouersweerw (Foortuftinge)") == "Foortuftinge"


def test_remark_of_a_later_variant_is_not_the_cells_remark():
    assert placelist.remark("Huađer; Huuger (Sölring; Wisinge)") == ""


# ------------------------------------------------------------- osm column ---
def test_parse_osm_reads_several_references_in_order():
    assert placelist.parse_osm("way/1347936331; node/1332249790") == [
        ("w", 1347936331), ("n", 1332249790)]


def test_parse_osm_does_not_need_a_space_after_the_semicolon():
    # places.csv has cells written that way (the Nordwarft on Ockholm)
    assert placelist.parse_osm("way/1347936331;node/1332249790") == [
        ("w", 1347936331), ("n", 1332249790)]


def test_parse_osm_of_an_empty_cell_is_no_reference():
    assert placelist.parse_osm("") == []
    assert placelist.parse_osm(None) == []


def test_parse_osm_reads_a_local_reference():
    assert placelist.parse_osm("local/westerheide-amrum") == [("l", "westerheide-amrum")]


@pytest.mark.parametrize("cell", [
    "way/abc",                        # not an id
    "Way/12",                         # types are lowercase
    "w/12",                           # the short type letter is internal only
    "https://www.openstreetmap.org/way/177387348",
    "local/Westerheide",              # slugs are lowercase
    "local/wester_heide",             # ... letters, digits and hyphens only
    "local/-westerheide",
])
def test_parse_osm_refuses_a_bad_reference(cell):
    with pytest.raises(SystemExit, match="bad reference"):
        placelist.parse_osm(cell, "places.csv:7")


def test_parse_osm_error_says_where():
    with pytest.raises(SystemExit, match="places.csv:7"):
        placelist.parse_osm("way/abc", "places.csv:7")


def test_a_local_reference_cannot_be_combined_with_others():
    with pytest.raises(SystemExit, match="stands alone"):
        placelist.parse_osm("local/westerheide-amrum; node/6928685546")


def test_two_local_references_cannot_be_combined_either():
    with pytest.raises(SystemExit, match="stands alone"):
        placelist.parse_osm("local/merlingmark; local/dreihardereck")


def test_format_osm_writes_the_cell_spelling():
    assert placelist.format_osm([("w", 1347936331), ("n", 1332249790)]) == \
        "way/1347936331; node/1332249790"
    assert placelist.format_osm([("r", 1420555)]) == "relation/1420555"
    assert placelist.format_osm([("l", "huelltoft")]) == "local/huelltoft"


@pytest.mark.parametrize("cell", [
    "node/240102263",
    "way/44051131; way/44051132; way/628205597",
    "relation/5615880",
    "local/westerheide-amrum",
])
def test_format_osm_round_trips_parse_osm(cell):
    assert placelist.format_osm(placelist.parse_osm(cell)) == cell


def test_format_osm_normalises_the_separator():
    assert placelist.format_osm(placelist.parse_osm("way/1347936331;node/1332249790")) == \
        "way/1347936331; node/1332249790"


# ------------------------------------------------------------- parse_point ---
def test_parse_point_returns_lon_then_lat():
    # arguments are (lat, lon) like the curation columns, the result is
    # (lon, lat) like GeoJSON and shapely
    assert placelist.parse_point("54.65097", "8.34019") == (8.34019, 54.65097)


def test_parse_point_ignores_surrounding_blanks():
    assert placelist.parse_point(" 54.881287 ", "8.771304 ") == (8.771304, 54.881287)


def test_parse_point_of_two_empty_cells_is_no_point():
    assert placelist.parse_point("", "") is None
    assert placelist.parse_point(None, None) is None


@pytest.mark.parametrize("lat,lon", [("54.65097", ""), ("", "8.34019")])
def test_parse_point_needs_both_cells(lat, lon):
    with pytest.raises(SystemExit, match="go together"):
        placelist.parse_point(lat, lon, "curation.csv:15")


@pytest.mark.parametrize("lat,lon", [
    ("54,65097", "8,34019"),          # a German spreadsheet's decimal comma
    ("54°39'N", "8°20'E"),
])
def test_parse_point_needs_decimal_degrees(lat, lon):
    with pytest.raises(SystemExit, match="not numbers"):
        placelist.parse_point(lat, lon)


@pytest.mark.parametrize("lat,lon", [("91", "8.3"), ("-90.5", "8.3"), ("54.6", "181"),
                                     ("54.6", "-180.01")])
def test_parse_point_refuses_coordinates_off_the_globe(lat, lon):
    with pytest.raises(SystemExit, match="out of range"):
        placelist.parse_point(lat, lon)


def test_parse_point_accepts_the_edges_of_the_globe():
    assert placelist.parse_point("-90", "180") == (180.0, -90.0)


# --------------------------------------------------- the real name list ---
def test_real_name_list_round_trips_byte_identical(tmp_path):
    """Reading and writing back the real places.csv changes nothing -- the
    guarantee that match.py and curate.py apply only ever touch the cells
    they mean to (a copy: the real file is never written)."""
    copy = tmp_path / "places.csv"
    shutil.copyfile(placelist.DEFAULT_PATH, copy)
    before = copy.read_bytes()
    rows, fields = placelist.read(str(copy))
    placelist.write(rows, str(copy), fields)
    assert copy.read_bytes() == before


# ------------------------------------------------------------ parse_set_tags ---
def test_set_tags_are_k_equals_v_pairs():
    assert placelist.parse_set_tags("place=island;frasch:kind=island") == {
        "place": "island", "frasch:kind": "island"}


def test_set_tags_ignore_blanks_and_empty_pairs():
    assert placelist.parse_set_tags(" place = island ;; ") == {"place": "island"}


def test_set_tags_value_may_contain_an_equals_sign():
    assert placelist.parse_set_tags("note=a=b") == {"note": "a=b"}


def test_set_tags_value_may_be_empty():
    assert placelist.parse_set_tags("name:de=") == {"name:de": ""}


def test_empty_set_tags_are_no_tags():
    assert placelist.parse_set_tags("") == {}
    assert placelist.parse_set_tags(None) == {}


def test_set_tags_entry_without_equals_is_refused():
    with pytest.raises(SystemExit, match="not key=value"):
        placelist.parse_set_tags("place=island;islet")


def test_set_tags_entry_with_empty_key_is_refused():
    with pytest.raises(SystemExit, match="empty key"):
        placelist.parse_set_tags("=island")


# ------------------------------------------------------------------- slug ---
@pytest.mark.parametrize("name, slug", [
    ("Schörkewärw", "schorkewarw"),
    ("Hamborjer Håli", "hamborjer-hali"),
    ("Straße", "strasse"),
    ("Æ Løkke", "ae-lokke"),
    ("Rudbøl", "rudbol"),
    ("Huađer", "huader"),
    ("Friedrich-Wilhelm-Lübke-Kuuch", "friedrich-wilhelm-lubke-kuuch"),
])
def test_slug_folds_a_name_to_lowercase_ascii(name, slug):
    assert placelist.slug(name) == slug
