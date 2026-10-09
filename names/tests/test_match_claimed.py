"""The matcher never gives a row an OSM object that a human already gave to
another row (#26, M4).  That is how two names came to claim way/28330569
and three other objects, of which only one can reach the map.  Nor does it
give two of its own rows one object or one Wikidata item (#94): the list
would be refused."""

from __future__ import annotations

import json
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
    return placelist.read(str(places), REGISTRY).rows


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


# ------------------------------------------------- two rows of the matcher ---
# the same dyke under a second name: the list has the place twice
LUNGDIIK = LUNGEDIK | {"mooring": "Lungdiik"}


def test_of_two_rows_for_one_place_the_first_gets_the_object(world: Path) -> None:
    first, _ = run_match(world, [LUNGEDIK, LUNGDIIK], [LANGERDEICH])
    assert (first["osm"], first["status"]) == ("way/28330569", "auto")


def test_of_two_rows_for_one_place_the_second_is_left_unmatched(world: Path) -> None:
    _, second = run_match(world, [LUNGEDIK, LUNGDIIK], [LANGERDEICH])
    assert (second["osm"], second["status"]) == ("", "")


def test_the_second_row_for_a_place_says_which_row_took_its_object(world: Path) -> None:
    run_match(world, [LUNGEDIK, LUNGDIIK], [LANGERDEICH])
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "way/28330569 is taken by line 2" in matches


def test_a_row_keeps_its_object_next_to_one_the_matcher_gave_another_row(world: Path) -> None:
    # the dyke lies at the hamlet and carries its name as `alt_name`: the row
    # of the dyke takes the dyke, not the whole place
    dyke = cand(
        "w",
        55824588,
        8.806919,
        54.762135,
        man_made="dyke",
        name="Deezbüll Deich",
        alt_name="Deezbülleck",
    )
    hamlet = cand("n", 10158150149, 8.800352, 54.763511, place="hamlet", name="Deezbülleck")
    rows = [
        {"kind": "warft", "mooring": "Deesbeldik", "de": "Deezbüll Deich"},
        {"kind": "warft", "mooring": "Deesbeljarn", "de": "Deezbülleck"},
    ]
    _, second = run_match(world, rows, [dyke, hamlet])
    assert (second["osm"], second["status"]) == ("node/10158150149", "auto")


def test_a_matched_row_that_lost_its_frisian_name_keeps_its_object(world: Path) -> None:
    # the matcher leaves such a row as it is, so its object is not free
    nameless = {"kind": "warft", "de": "Langedeich", "osm": "way/28330569", "status": "auto"}
    _, row = run_match(world, [nameless, LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("", "")


def test_of_two_country_rows_for_one_item_the_second_is_left_unmatched(world: Path) -> None:
    cache = world / "work" / "wikidata-countries.json"
    cache.write_text(json.dumps({"Dänemark": "Q35"}), encoding="utf-8")
    denmark = {"kind": "country", "mooring": "Däänemark", "de": "Dänemark"}
    _, second = run_match(world, [denmark, denmark | {"mooring": "Dånmark"}], [])
    assert (second["wikidata"], second["status"]) == ("", "")


# A country row Wikidata gave no answer for is left as it is (`--offline`,
# and its name is not in the cache), so it still holds its item.
UNANSWERED = {
    "kind": "country",
    "mooring": "Däänemark",
    "de": "Dänemark",
    "wikidata": "Q35",
    "status": "auto",
}


def rows_after_a_failed_lookup(
    world: Path, rows: Iterable[Mapping[str, str]], candidates: Iterable[Candidate]
) -> list[placelist.PlaceRow]:
    """The name list after a run that could not look `UNANSWERED` up."""
    places = world / "places.csv"
    places.write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", *candidates)
    cache = world / "work" / "wikidata-countries.json"
    cache.write_text(json.dumps({"Danmark": "Q35"}), encoding="utf-8")
    assert match.run(workspace(world), REGISTRY, offline=True) == 1
    return placelist.read(str(places), REGISTRY).rows


def test_the_item_of_a_country_row_left_unanswered_goes_to_no_later_row(world: Path) -> None:
    danish = {"kind": "country", "mooring": "Dånmark", "de": "Danmark"}
    _, second = rows_after_a_failed_lookup(world, [UNANSWERED, danish], [])
    assert (second["wikidata"], second["status"]) == ("", "")


def test_the_item_of_a_country_row_left_unanswered_goes_to_no_earlier_row(world: Path) -> None:
    # the island's object carries the item; its row stands above the country's
    jutland = cand("r", 1, 9.2, 55.6, place="island", name="Jütland", wikidata="Q35")
    island = {"kind": "island", "mooring": "Jütlönj", "de": "Jütland"}
    first, _ = rows_after_a_failed_lookup(world, [island, UNANSWERED], [jutland])
    assert (first["osm"], first["wikidata"]) == ("relation/1", "")


def test_the_second_country_row_for_an_item_says_which_row_took_it(world: Path) -> None:
    cache = world / "work" / "wikidata-countries.json"
    cache.write_text(json.dumps({"Dänemark": "Q35"}), encoding="utf-8")
    denmark = {"kind": "country", "mooring": "Däänemark", "de": "Dänemark"}
    run_match(world, [denmark, denmark | {"mooring": "Dånmark"}], [])
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "Q35 is taken by line 2" in matches


def test_a_row_written_without_another_rows_item_says_which_row_holds_it(world: Path) -> None:
    pellworm = [
        cand("r", 1, 8.64, 54.52, place="island", name="Pellworm", wikidata="Q21044"),
        cand("n", 2, 8.65, 54.53, place="village", name="Pellworm", wikidata="Q21044"),
    ]
    island = {"kind": "island", "mooring": "Pälweerm", "de": "Pellworm"}
    village = {"kind": "settlement", "mooring": "Pälweerm", "de": "Pellworm"}
    run_match(world, [island, village], pellworm)
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "Q21044 is taken by line 2" in matches


def test_a_row_whose_object_carries_another_rows_item_keeps_the_object_without_it(
    world: Path,
) -> None:
    # OSM tags the island and its village with the one Wikidata item they share
    pellworm = [
        cand("r", 1, 8.64, 54.52, place="island", name="Pellworm", wikidata="Q21044"),
        cand("n", 2, 8.65, 54.53, place="village", name="Pellworm", wikidata="Q21044"),
    ]
    island = {"kind": "island", "mooring": "Pälweerm", "de": "Pellworm"}
    village = {"kind": "settlement", "mooring": "Pälweerm", "de": "Pellworm"}
    _, second = run_match(world, [island, village], pellworm)
    assert (second["osm"], second["wikidata"]) == ("node/2", "")
