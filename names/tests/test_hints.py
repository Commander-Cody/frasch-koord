"""hints.py: the circle a row's location hint narrows its match down to --
which place of the hint's name it means, and how wide the circle is.  The
fixed circles, a large island and the first of several hints are tested
through the matches file (test_match_output.py)."""

from __future__ import annotations

from frasch.candidates import Candidate
from frasch.hints import HintResolver
from frasch.nameindex import NameIndex
from conftest import cand


def resolve(hint: str, *recs: Candidate) -> tuple[float, float, float] | None:
    return HintResolver(NameIndex(recs)).resolve(hint)


def test_a_small_island_narrows_the_hint_to_ten_km() -> None:
    hooge = cand("n", 1, 8.55, 54.57, name="Hooge", place="island")
    assert resolve("Hooge", hooge) == (8.55, 54.57, 10.0)


def test_of_two_villages_of_the_name_the_one_nearer_to_north_frisia_is_meant() -> None:
    far = cand("n", 1, 10.5, 54.3, name="Holm", place="village")
    near = cand("n", 2, 8.87, 54.83, name="Holm", place="village")
    assert resolve("Holm", far, near) == (8.87, 54.83, 8.0)


def test_an_island_is_meant_before_a_nearer_place_of_its_name_that_is_none() -> None:
    # a field name in the middle of North Frisia, the island 15 km away
    field = cand("n", 1, 8.9, 54.7, name="Oland", place="locality")
    island = cand("n", 2, 8.69, 54.67, name="Oland", place="island")
    assert resolve("Oland", field, island) == (8.69, 54.67, 10.0)


def test_an_object_of_the_name_that_is_no_place_is_no_hint() -> None:
    shop = cand("n", 1, 8.87, 54.83, name="Holm", shop="bakery")
    assert resolve("Holm", shop) is None


def test_a_place_of_the_name_without_a_position_is_no_hint() -> None:
    nowhere = cand("r", 1, None, None, name="Holm", place="village")
    assert resolve("Holm", nowhere) is None
