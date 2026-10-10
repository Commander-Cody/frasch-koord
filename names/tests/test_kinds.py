"""kinds.py: what each kind of the name list means to the pipeline."""

from __future__ import annotations

import pytest

from frasch import kinds
from conftest import cand


# ---------------------------------------------------------------- accepts ---
@pytest.mark.parametrize(
    "kind,tags,ok",
    [
        ("settlement", {"place": "village"}, True),
        ("settlement", {"highway": "residential"}, False),  # the street "Holm"
        ("settlement", {"boundary": "administrative", "admin_level": "8"}, True),
        ("settlement", {"boundary": "administrative", "admin_level": "4"}, False),  # a Land
        ("hallig", {"place": "isolated_dwelling"}, True),  # some Halligen are one dwelling
        ("island", {"place": "isolated_dwelling"}, False),
        ("island", {"natural": "peninsula"}, True),  # Nordstrand
        ("warft", {"landuse": "residential"}, True),
        ("warft", {"highway": "service"}, False),
        ("water", {"waterway": "river"}, True),
        ("road", {"highway": "unclassified"}, True),
        ("road", {"place": "village"}, False),
        ("country", {"boundary": "administrative", "admin_level": "2"}, True),
        ("country", {"boundary": "administrative", "admin_level": "4"}, False),
    ],
)
def test_a_kind_accepts_the_objects_that_can_be_one_of_it(
    kind: str, tags: dict[str, str], ok: bool
) -> None:
    assert kinds.rule(kind).accepts(tags) is ok


# -------------------------------------------------------------- canonical ---
def test_a_rivers_relation_stands_for_the_ways_it_groups() -> None:
    piece = cand("w", 1, 9.0, 54.6, name="Arlau", waterway="river")
    river = cand("r", 2, 9.0, 54.6, name="Arlau", type="waterway", waterway="river")
    assert kinds.rule("water").canonical([piece, river]) == [river]


def test_a_lake_is_its_area_where_no_relation_groups_it() -> None:
    lake = cand("w", 1, 9.0, 54.6, name="Bottschlotter See", natural="water")
    ditch = cand("w", 2, 9.0, 54.6, name="Bottschlotter See", waterway="ditch")
    assert kinds.rule("water").canonical([ditch, lake]) == [lake]


def test_a_settlements_place_stands_for_its_boundary() -> None:
    village = cand("n", 1, 8.8, 54.8, name="Holm", place="village")
    municipality = cand("r", 2, 8.8, 54.8, name="Holm", boundary="administrative")
    assert kinds.rule("settlement").canonical([municipality, village]) == [village]


def test_an_islands_outline_stands_for_its_place_node() -> None:
    label = cand("n", 1, 8.5, 54.6, name="Hooge", place="island")
    outline = cand("w", 2, 8.5, 54.6, name="Hooge", place="island")
    assert kinds.rule("hallig").canonical([label, outline]) == [outline]


def test_candidates_without_a_canonical_object_all_stay() -> None:
    pieces = [cand("w", i, 9.0, 54.6, name="Arlau", waterway="river") for i in (1, 2)]
    assert kinds.rule("water").canonical(pieces) == pieces


# ------------------------------------------------------------------ bonus ---
def test_a_peninsulas_outline_suits_an_island_as_well_as_an_islands_does() -> None:
    peninsula = cand("w", 1, 8.86, 54.49, name="Nordstrand", natural="peninsula")
    island = cand("w", 2, 8.54, 54.57, name="Hooge", place="island")
    assert kinds.rule("island").bonus(peninsula) == kinds.rule("island").bonus(island)


def test_a_settlements_place_node_suits_it_better_than_its_boundary() -> None:
    village = cand("n", 1, 8.8, 54.8, name="Holm", place="village")
    municipality = cand("r", 2, 8.8, 54.8, name="Holm", boundary="administrative")
    settlement = kinds.rule("settlement")
    assert settlement.bonus(village) > settlement.bonus(municipality)


def test_an_islands_outline_suits_it_better_than_its_place_node() -> None:
    label = cand("n", 1, 8.5, 54.6, name="Hooge", place="island")
    outline = cand("w", 2, 8.5, 54.6, name="Hooge", place="island")
    assert kinds.rule("island").bonus(outline) > kinds.rule("island").bonus(label)


def test_a_road_is_a_way_rather_than_a_node_on_it() -> None:
    street = cand("w", 1, 8.8, 54.8, name="Dorfstraße", highway="residential")
    junction = cand("n", 2, 8.8, 54.8, name="Dorfstraße", highway="motorway_junction")
    assert kinds.rule("road").bonus(street) > kinds.rule("road").bonus(junction)
