"""The matcher never gives a row an OSM object that a human already gave to
another row (#26, M4).  That is how two names came to claim way/28330569
and three other objects, of which only one can reach the map."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from frasch import placelist
from frasch import match
from frasch.candidates import Candidate
from conftest import REGISTRY, cand, places_text, workspace, write_candidates

LANGERDEICH = cand(
    "w", 28330569, 8.865771, 54.471785, man_made="dyke", highway="residential", name="Langerdeich"
)
LUNGEDIK = {"kind": "warft", "mooring": "Lungedik", "de": "Langerdeich"}


def run_match(
    world: Path, rows: Iterable[Mapping[str, str]], candidates: Iterable[Candidate]
) -> list[placelist.PlaceRow]:
    places = world / "places.csv"
    places.write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", *candidates)
    assert match.run(workspace(world), REGISTRY, offline=True) == 0
    return placelist.read(str(places), REGISTRY)[0]


def test_an_unclaimed_object_is_matched(world: Path) -> None:
    [row] = run_match(world, [LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("way/28330569", "auto")


def test_an_object_a_human_gave_to_another_row_is_not_matched_again(world: Path) -> None:
    checked = {
        "kind": "warft",
        "mooring": "Lungendik",
        "de": "Langedeich",
        "osm": "way/28330569",
        "status": "ok",
    }
    _, row = run_match(world, [checked, LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("", "")


def test_a_skipped_row_does_not_claim_its_object(world: Path) -> None:
    # `skip` rows never reach the map, so their object is free.
    skipped = {
        "kind": "warft",
        "mooring": "Lungendik",
        "de": "Langedeich",
        "osm": "way/28330569",
        "status": "skip",
    }
    _, row = run_match(world, [skipped, LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("way/28330569", "auto")


def test_the_rest_of_a_river_a_human_gave_in_part_to_another_row_is_not_matched(
    world: Path,
) -> None:
    # The Arlau is split into several ways.  A checked row holding one of
    # them names the river already; handing this row the other pieces would
    # label one river with two names.
    pieces = [
        cand("w", i, 9.0, 54.6 + 0.01 * i, name="Arlau", waterway="river")
        for i in (44051131, 44051132, 44051133)
    ]
    checked = {
        "kind": "water",
        "mooring": "Arlou",
        "de": "Arlau",
        "osm": "way/44051131",
        "status": "ok",
    }
    second = {"kind": "water", "mooring": "Äarlou", "de": "Arlau"}
    _, row = run_match(world, [checked, second], pieces)
    assert (row["osm"], row["status"]) == ("", "")
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "way/44051131 is taken by line 2" in matches


def test_a_river_whose_relation_a_human_gave_to_another_row_is_not_matched(world: Path) -> None:
    # The Schmale is two ways and a type=waterway relation grouping them.
    # A checked row holding just the relation names the whole river; the
    # relation has no waterway tag of its own, which must not hide that.
    schmale = [
        cand("w", 145819821, 8.782303, 54.86851, name="Schmale", waterway="river"),
        cand("w", 836479122, 8.768417, 54.891347, name="Schmale", waterway="river"),
        cand(
            "r",
            18140519,
            8.779962,
            54.847824,
            name="Schmale",
            type="waterway",
            wikidata="Q130468878",
        ),
    ]
    checked = {
        "kind": "water",
        "mooring": "e Smeele",
        "de": "Schmale",
        "osm": "relation/18140519",
        "status": "ok",
    }
    second = {"kind": "water", "mooring": "e Smeerle", "de": "Schmale"}
    _, row = run_match(world, [checked, second], schmale)
    assert (row["osm"], row["status"]) == ("", "")
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "relation/18140519 is taken by line 2" in matches
