"""The matcher never gives a row an OSM object that a human already gave to
another row (#26, M4).  That is how two names came to claim way/28330569
and three other objects, of which only one can reach the map."""
from __future__ import annotations

import placelist
import match
from conftest import cand, places_text, write_candidates

LANGERDEICH = cand("w", 28330569, 8.865771, 54.471785, man_made="dyke",
                   highway="residential", name="Langerdeich")
LUNGEDIK = {"kind": "warft", "mooring": "Lungedik", "de": "Langerdeich"}


def run_match(world, rows, candidates):
    places = world / "places.csv"
    places.write_text(places_text(rows), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", *candidates)
    code = match.main(["--names", str(places),
                       "--candidates", str(world / "work" / "candidates.jsonl"),
                       "--matches", str(world / "work" / "matches.csv"),
                       "--report", str(world / "REPORT.md"), "--offline",
                       "--wikidata-cache", str(world / "work" / "wd.json")])
    assert code == 0
    return placelist.read(str(places))[0]


def test_an_unclaimed_object_is_matched(world):
    [row] = run_match(world, [LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("way/28330569", "auto")


def test_an_object_a_human_gave_to_another_row_is_not_matched_again(world):
    checked = {"kind": "warft", "mooring": "Lungendik", "de": "Langedeich",
               "osm": "way/28330569", "status": "ok"}
    _, row = run_match(world, [checked, LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("", "")


def test_a_skipped_row_does_not_claim_its_object(world):
    # `skip` rows never reach the map, so their object is free.
    skipped = {"kind": "warft", "mooring": "Lungendik", "de": "Langedeich",
               "osm": "way/28330569", "status": "skip"}
    _, row = run_match(world, [skipped, LUNGEDIK], [LANGERDEICH])
    assert (row["osm"], row["status"]) == ("way/28330569", "auto")


def test_the_rest_of_a_river_a_human_gave_in_part_to_another_row_is_not_matched(world):
    # The Arlau is split into several ways.  A checked row holding one of
    # them names the river already; handing this row the other pieces would
    # label one river with two names.
    pieces = [cand("w", i, 9.0, 54.6 + 0.01 * i, name="Arlau", waterway="river")
              for i in (44051131, 44051132, 44051133)]
    checked = {"kind": "water", "mooring": "Arlou", "de": "Arlau",
               "osm": "way/44051131", "status": "ok"}
    second = {"kind": "water", "mooring": "Äarlou", "de": "Arlau"}
    _, row = run_match(world, [checked, second], pieces)
    assert (row["osm"], row["status"]) == ("", "")
    matches = (world / "work" / "matches.csv").read_text(encoding="utf-8")
    assert "way/44051131 is taken by line 2" in matches
