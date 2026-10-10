"""placenames.py: which names and attributes a place gets (README "The shared
name logic") -- the one rule the tiles and the search index are built by."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from shapely.geometry import box

from frasch import placelist, placenames
from frasch.__main__ import main
from frasch.dialect_areas import AreaIndex
from frasch.objects import LocatedObject
from conftest import REGISTRY

# four dialect areas side by side, and a point in each
AREAS = AreaIndex(
    [
        ("frr-x-mooring", box(8, 54, 9, 55)),
        ("frr-x-nordgoes", box(9, 54, 10, 55)),
        ("frr-x-hallig", box(10, 54, 11, 55)),
        ("frr-x-solring", box(11, 54, 12, 55)),
    ]
)
IN_MOORING: LocatedObject = {"lon": 8.5, "lat": 54.5}
IN_NORDGOES: LocatedObject = {"lon": 9.5, "lat": 54.5}
IN_HALLIG: LocatedObject = {"lon": 10.5, "lat": 54.5}
IN_SOLRING: LocatedObject = {"lon": 11.5, "lat": 54.5}
OUTSIDE: LocatedObject = {"lon": 0.0, "lat": 0.0}


def row(**cells: str) -> dict[str, str]:
    return {c: "" for c in placelist.columns(REGISTRY)} | cells


def resolve(obj: LocatedObject | None, place: Mapping[str, str]) -> placenames.PlaceNames:
    return placenames.resolve(place, obj, AREAS, REGISTRY)


# Hanswarft on Hooge: the Mooring name is the foreign form, the Hallig one is
# what the people there say (README "Dialect areas")
HANSWARFT = row(id="hanswarw", kind="warft", mooring="Hanswärw", hallig="Hansweerf", de="Hanswarft")


# ------------------------------------------------------ the dialect names ---
def test_a_place_has_the_name_of_every_dialect_that_has_one_for_it() -> None:
    assert resolve(OUTSIDE, HANSWARFT).names == {
        "frr-x-mooring": "Hanswärw",
        "frr-x-hallig": "Hansweerf",
    }


def test_a_dialects_name_is_the_primary_variant_of_its_column() -> None:
    schorkewarw = row(kind="hallig", hallig="Schorkeweerw; Nees-Schorkeweerw")
    assert resolve(OUTSIDE, schorkewarw).names == {"frr-x-hallig": "Schorkeweerw"}


# Broderswarft, Fahretoft: a sub-dialect form in `local` with its variety
BRODERSWARFT = row(
    id="brouderswarw",
    kind="warft",
    mooring="Brouderswärw",
    local="Brouersweerw (Foortuftinge)",
    de="Broderswarft",
)


def test_the_dialect_of_the_places_own_area_falls_back_to_the_local_form() -> None:
    # the Foortuftinge form IS the name in the dialect spoken at Fahretoft
    assert resolve(IN_NORDGOES, BRODERSWARFT).names["frr-x-nordgoes"] == "Brouersweerw"


def test_another_dialect_does_not_fall_back_to_the_local_form() -> None:
    assert "frr-x-wieding" not in resolve(IN_NORDGOES, BRODERSWARFT).names


def test_outside_every_area_no_dialect_falls_back_to_the_local_form() -> None:
    assert "frr-x-nordgoes" not in resolve(OUTSIDE, BRODERSWARFT).names


def test_a_dialects_own_column_wins_over_the_local_form() -> None:
    assert resolve(IN_MOORING, BRODERSWARFT).names["frr-x-mooring"] == "Brouderswärw"


# --------------------------------------------------------- the local name ---
def test_the_local_name_is_the_local_column_first() -> None:
    assert resolve(IN_MOORING, BRODERSWARFT).local == "Brouersweerw"


def test_the_local_name_is_the_local_column_also_outside_every_area() -> None:
    assert resolve(OUTSIDE, BRODERSWARFT).local == "Brouersweerw"


def test_the_local_name_falls_back_to_the_name_in_the_areas_dialect() -> None:
    assert resolve(IN_HALLIG, HANSWARFT).local == "Hansweerf"


def test_without_a_local_form_there_is_no_local_name_outside_every_area() -> None:
    assert resolve(OUTSIDE, HANSWARFT).local == ""


def test_there_is_no_local_name_where_the_areas_dialect_has_none() -> None:
    # a Mooring-only row on Sylt: no Sölring form known, nothing local to say
    muasem = row(kind="settlement", mooring="Muasem", de="Morsum")
    assert resolve(IN_SOLRING, muasem).local == ""


def test_osms_frisian_name_is_the_local_name_of_a_place_the_list_gives_none() -> None:
    # inside a dialect area it is almost always the form the place itself uses (#81)
    muasem = row(kind="settlement", mooring="Muasem", de="Morsum")
    assert resolve(IN_SOLRING | {"name_frr": "Muasem"}, muasem).local == "Muasem"


def test_outside_every_area_osms_frisian_name_is_an_exonym_and_no_local_name() -> None:
    pinneberg = row(kind="settlement", mooring="Pinebärj", de="Pinneberg")
    assert resolve(OUTSIDE | {"name_frr": "Pinebärj"}, pinneberg).local == ""


def test_the_lists_local_name_wins_over_osms_frisian_name() -> None:
    assert resolve(IN_HALLIG | {"name_frr": "Hanswarf"}, HANSWARFT).local == "Hansweerf"


def test_a_local_name_taken_from_osm_is_marked_as_such() -> None:
    muasem = row(kind="settlement", mooring="Muasem", de="Morsum")
    assert resolve(IN_SOLRING | {"name_frr": "Muasem"}, muasem).local_from_osm


def test_a_local_name_of_the_list_is_not_marked_as_osms() -> None:
    assert not resolve(IN_HALLIG | {"name_frr": "Hanswarf"}, HANSWARFT).local_from_osm


def test_an_object_no_row_claims_has_osms_frisian_name_as_its_local_name() -> None:
    # a Warft, a street, a station inside a dialect area (#81)
    kirchwarft: LocatedObject = IN_HALLIG | {"name_frr": "Schörkeweerw"}
    assert placenames.unclaimed_local(kirchwarft, AREAS) == "Schörkeweerw"


# ------------------------------------------------------- the other fields ---
def test_a_place_has_the_dialect_of_the_area_it_lies_in() -> None:
    assert resolve(IN_HALLIG, HANSWARFT).dialect == "frr-x-hallig"


def test_a_place_outside_every_area_has_no_dialect() -> None:
    assert resolve(OUTSIDE, HANSWARFT).dialect == ""


def test_an_object_of_unknown_position_has_no_dialect() -> None:
    # a way or relation found through its Wikidata QID alone
    assert resolve(None, HANSWARFT).dialect == ""


def test_the_variety_is_the_remark_on_the_local_form() -> None:
    assert resolve(IN_MOORING, BRODERSWARFT).variety == "Foortuftinge"


def test_the_german_name_is_the_first_variant_of_the_lists() -> None:
    # as the card's German step reads it (#61)
    listlai = row(id="listlai", kind="water", solring="Listlai", de="Lister Ley; Ley")
    assert resolve(OUTSIDE, listlai).name_de == "Lister Ley"


def test_a_place_is_named_by_the_id_of_its_row() -> None:
    # not by the object: the search index names the place by the row (#23)
    assert resolve(OUTSIDE, HANSWARFT).id == "hanswarw"


def test_a_place_has_the_kind_of_its_row() -> None:
    assert resolve(OUTSIDE, HANSWARFT).kind == "warft"


# ----------------------------------------------------- as tags of a tile ---
def test_the_tags_of_a_place_are_its_names_under_their_tile_keys() -> None:
    names = resolve(IN_MOORING, BRODERSWARFT)
    assert placenames.as_tags(names) == {
        "name:frr-x-mooring": "Brouderswärw",
        "name:de": "Broderswarft",
        "frasch:kind": "warft",
        "frasch:dialect": "frr-x-mooring",
        "frasch:local": "Brouersweerw",
        "frasch:variety": "Foortuftinge",
        "frasch:ref": "brouderswarw",
    }


def test_a_place_gets_no_tag_for_what_it_has_none_of() -> None:
    # outside every area, without a local form: no dialect, local name or variety
    assert placenames.as_tags(resolve(OUTSIDE, HANSWARFT)) == {
        "name:frr-x-mooring": "Hanswärw",
        "name:frr-x-hallig": "Hansweerf",
        "name:de": "Hanswarft",
        "frasch:kind": "warft",
        "frasch:ref": "hanswarw",
    }


# ------------------------------------------- as an entry of the search index ---
def test_the_entry_of_a_place_is_its_names_where_its_object_lies() -> None:
    names = resolve(IN_MOORING, BRODERSWARFT)
    assert placenames.as_entry(names, IN_MOORING, BRODERSWARFT) == {
        "id": "brouderswarw",
        "names": {"frr-x-mooring": "Brouderswärw"},
        "name_de": "Broderswarft",
        "lon": 8.5,
        "lat": 54.5,
        "kind": "warft",
        "local": "Brouersweerw",
        "dialect": "frr-x-mooring",
        "variety": "Foortuftinge",
    }


def test_an_entry_leaves_out_what_the_place_has_none_of() -> None:
    entry = placenames.as_entry(resolve(OUTSIDE, HANSWARFT), OUTSIDE, HANSWARFT)
    assert sorted(entry) == ["id", "kind", "lat", "lon", "name_de", "names"]


def test_an_entrys_position_has_five_decimals() -> None:
    # about a metre: what a search result needs to fly to
    obj: LocatedObject = {"lon": 8.1234567, "lat": 54.7654321}
    entry = placenames.as_entry(resolve(obj, HANSWARFT), obj, HANSWARFT)
    assert (entry["lon"], entry["lat"]) == (8.12346, 54.76543)


def test_an_entry_carries_osms_names_of_its_object_and_the_rows_own_facts() -> None:
    # none of them the name rule's: the label chain and the card's links need them
    ripen = row(
        id="ripen", kind="settlement", mooring="Ripen", da="Ribe", osm="node/1", wikidata="Q322"
    )
    obj: LocatedObject = {"lon": 8.76, "lat": 55.33, "name": "Ribe", "name_nds": "Riep"}
    entry = placenames.as_entry(resolve(obj, ripen), obj, ripen)
    own = ("name_nds", "name_osm", "name_da", "osm", "wikidata")
    assert {field: entry.get(field) for field in own} == {
        "name_nds": "Riep",
        "name_osm": "Ribe",
        "name_da": "Ribe",
        "osm": "node/1",
        "wikidata": "Q322",
    }


# --------------------------------------------------- the table of tile keys ---
@pytest.mark.parametrize("field", placenames.TILE_KEY)
def test_an_entrys_field_and_its_tile_key_say_the_same(field: str) -> None:
    # Broderswarft has a value for every field of the table
    names = resolve(IN_MOORING, BRODERSWARFT)
    entry = placenames.as_entry(names, IN_MOORING, BRODERSWARFT)
    assert entry.get(field) == placenames.as_tags(names)[placenames.TILE_KEY[field]]


# -------------------------------------------------------------- the command ---
def test_the_command_prints_the_attribute_keys_planetiler_has_to_pass_through(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # the `name:<language>` keys are not among them: its --languages carries those
    main(["tile-keys"])
    assert sorted(capsys.readouterr().out.strip().split(",")) == [
        "frasch:dialect",
        "frasch:kind",
        "frasch:local",
        "frasch:maxzoom",
        "frasch:minzoom",
        "frasch:ref",
        "frasch:variety",
    ]
