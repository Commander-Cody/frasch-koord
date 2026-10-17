"""The matcher never gives a row an OSM object that a human already gave to
another row (#26, M4).  That is how two names came to claim way/28330569
and three other objects, of which only one can reach the map.  Nor does it
give two of its own rows one object or one Wikidata item (#94): the list
would be refused."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from frasch import match, matchfile, placelist
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


def why(world: Path, row_id: str) -> str:
    """The matcher's remark on a row of the last run."""
    return next(
        m["why"] for m in matchfile.read(world / "work" / "matches.jsonl") if m["id"] == row_id
    )


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
        cand("w", i, 9.0, 54.6 + 0.01 * n, name="Arlau", waterway="river")
        for n, i in enumerate((44051131, 44051132, 44051133))
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
    assert why(world, "row-2") == "way/44051131 is taken by row row-1"


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
    assert why(world, "row-2") == "relation/18140519 is taken by row row-1"


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
    assert why(world, "row-2") == "way/28330569 is taken by row row-1"


# the Arlau as a relation that is tagged as the river itself, and its ways
ARLAU_RELATION = cand("r", 2389612, 9.0, 54.62, name="Arlau", type="waterway", waterway="river")
ARLAU_WAYS = [cand("w", i, 9.0, 54.6 + 0.01 * i, name="Arlau", waterway="river") for i in (1, 2, 3)]
ARLOU = {"kind": "water", "mooring": "Arlou", "de": "Arlau"}


def test_of_two_rows_for_one_river_the_second_gets_no_other_object_of_it(world: Path) -> None:
    # the first row gets the relation; the river's ways are not free for a second name
    _, second = run_match(
        world, [ARLOU, ARLOU | {"mooring": "Äarlou"}], [ARLAU_RELATION, *ARLAU_WAYS]
    )
    assert (second["osm"], second["status"]) == ("", "")


def test_the_second_row_for_a_river_says_which_row_took_it(world: Path) -> None:
    run_match(world, [ARLOU, ARLOU | {"mooring": "Äarlou"}], [ARLAU_RELATION, *ARLAU_WAYS])
    assert why(world, "row-2") == "relation/2389612 is taken by row row-1"


def test_of_two_rows_for_one_village_the_second_gets_no_other_object_of_it(world: Path) -> None:
    # the first row gets the place node; its municipality is the same village
    holm = [
        cand("n", 240102263, 8.866668, 54.833305, name="Holm", place="village"),
        cand(
            "r",
            1420394,
            8.857041,
            54.831964,
            name="Holm",
            boundary="administrative",
            admin_level="8",
        ),
    ]
    hulm = {"kind": "settlement", "mooring": "Hulm", "de": "Holm"}
    _, second = run_match(world, [hulm, hulm | {"mooring": "Holem"}], holm)
    assert (second["osm"], second["status"]) == ("", "")


# the dyke lies at the hamlet and carries its name as `alt_name`
DEEZBUELL_DYKE = cand(
    "w",
    55824588,
    8.806919,
    54.762135,
    man_made="dyke",
    name="Deezbüll Deich",
    alt_name="Deezbülleck",
)
DEEZBUELLECK = cand("n", 10158150149, 8.800352, 54.763511, place="hamlet", name="Deezbülleck")
DEESBELJARN = {"kind": "warft", "mooring": "Deesbeljarn", "de": "Deezbülleck"}


def test_a_row_keeps_its_object_next_to_one_the_matcher_gave_another_row(world: Path) -> None:
    # the row of the dyke takes the dyke, not the whole place
    dyke_row = {"kind": "warft", "mooring": "Deesbeldik", "de": "Deezbüll Deich"}
    _, second = run_match(world, [dyke_row, DEESBELJARN], [DEEZBUELL_DYKE, DEEZBUELLECK])
    assert (second["osm"], second["status"]) == ("node/10158150149", "auto")


def test_a_dyke_a_human_gave_to_another_row_holds_the_hamlet_it_also_names(world: Path) -> None:
    # the word of a row a human decided reaches over its whole feature, by
    # whatever name the second row finds the object
    checked = {"kind": "warft", "mooring": "Deesbeldik", "de": "Deezbüll Deich"} | {
        "osm": "way/55824588",
        "status": "ok",
    }
    run_match(world, [checked, DEESBELJARN], [DEEZBUELL_DYKE, DEEZBUELLECK])
    assert why(world, "row-2") == "way/55824588 is taken by row row-1"


def test_an_object_found_by_an_annotated_name_of_its_own_holds_its_feature(world: Path) -> None:
    # `Klockries (NF)` is the village's own short name, though the hit on it
    # ranks no better than one on an `alt_name`
    klockries = [
        cand(
            "n", 1, 8.83, 54.75, place="village", name="Klockries-Dorf", short_name="Klockries (NF)"
        ),
        cand("r", 2, 8.84, 54.755, name="Klockries", boundary="administrative", admin_level="8"),
    ]
    rows = [
        {"kind": "settlement", "mooring": "Klookriis-Toorp", "de": "Klockries-Dorf"},
        {"kind": "settlement", "mooring": "Klookriis", "de": "Klockries"},
    ]
    run_match(world, rows, klockries)
    assert why(world, "row-2") == "node/1 is taken by row row-1"


def test_an_object_one_of_a_rows_names_finds_by_a_name_of_its_own_holds_its_feature(
    world: Path,
) -> None:
    # the second row's `Holm` is the village's own name; that its `Holme`
    # finds the village only as an `alt_name` takes nothing from that
    holm = [
        cand("n", 240102263, 8.866668, 54.833305, name="Holm", alt_name="Holme", place="village"),
        cand(
            "r",
            1420394,
            8.857041,
            54.831964,
            name="Holm",
            boundary="administrative",
            admin_level="8",
        ),
    ]
    rows = [
        {"kind": "settlement", "mooring": "Hulm", "de": "Holm"},
        {"kind": "settlement", "mooring": "Holem", "de": "Holm; Holme"},
    ]
    run_match(world, rows, holm)
    assert why(world, "row-2") == "node/240102263 is taken by row row-1"


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
    assert why(world, "row-2") == "Q35 is taken by row row-1"


def test_a_row_written_without_another_rows_item_says_which_row_holds_it(world: Path) -> None:
    pellworm = [
        cand("r", 1, 8.64, 54.52, place="island", name="Pellworm", wikidata="Q21044"),
        cand("n", 2, 8.65, 54.53, place="village", name="Pellworm", wikidata="Q21044"),
    ]
    island = {"kind": "island", "mooring": "Pälweerm", "de": "Pellworm"}
    village = {"kind": "settlement", "mooring": "Pälweerm", "de": "Pellworm"}
    run_match(world, [island, village], pellworm)
    assert why(world, "row-2") == "Q21044 is taken by row row-1"


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
