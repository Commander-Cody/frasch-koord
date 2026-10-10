"""osmtags.py: what the pipeline makes of an OSM object's tags."""

from __future__ import annotations

from frasch import osmtags


# --------------------------------------------------------------- class_of ---
def test_the_class_of_an_object_is_the_value_of_its_class_tag() -> None:
    assert osmtags.class_of({"name": "Toftum", "place": "village"}) == "village"


def test_an_island_drawn_as_its_coastline_is_an_island() -> None:
    # Hooge, way 1472528450
    assert osmtags.class_of({"natural": "coastline", "place": "island"}) == "island"


def test_an_object_without_a_class_tag_has_no_class() -> None:
    assert osmtags.class_of({"name": "Kiosk", "shop": "kiosk"}) == ""


# --------------------------------------------------------------- decisive ---
def test_the_decisive_tags_are_the_class_tags_and_what_narrows_them_down() -> None:
    municipality = {
        "name": "Kampen (Sylt)",
        "admin_level": "8",
        "boundary": "administrative",
        "type": "boundary",
        "wikidata": "Q27332",
    }
    assert osmtags.decisive(municipality) == "boundary=administrative;admin_level=8;type=boundary"
