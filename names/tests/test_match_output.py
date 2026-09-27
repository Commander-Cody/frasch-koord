"""match.py's worklist -- work/matches.csv and REPORT.md -- names a row by its
id, which stays put when rows are added above it (#23)."""
from __future__ import annotations

import csv

import match
from conftest import cand, places_text, write_candidates

TOFTUM = cand("n", 240044107, 8.83, 54.71, place="village", name="Toftum")
UPHUSUM = [cand("n", 1, 8.90, 54.70, place="hamlet", name="Uphusum"),
           cand("n", 2, 8.95, 54.75, place="hamlet", name="Uphusum")]
ROWS = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    {"id": "aphusem-2", "kind": "settlement", "mooring": "Aphüsem", "de": "Uphusum"},
]


def run_match(world):
    places = world / "places.csv"
    places.write_text(places_text(ROWS), encoding="utf-8")
    write_candidates(world / "work" / "candidates.jsonl", TOFTUM, *UPHUSUM)
    code = match.main(["--names", str(places),
                       "--candidates", str(world / "work" / "candidates.jsonl"),
                       "--matches", str(world / "work" / "matches.csv"),
                       "--report", str(world / "REPORT.md"), "--offline",
                       "--wikidata-cache", str(world / "work" / "wd.json")])
    assert code == 0


def test_matches_csv_keys_each_row_by_its_id(world):
    run_match(world)
    with open(world / "work" / "matches.csv", encoding="utf-8", newline="") as fh:
        got = [(m["id"], m["line"], m["result"]) for m in csv.DictReader(fh)]
    assert got == [("toftem", "2", "matched"), ("aphusem-2", "3", "ambiguous")]


def test_the_report_names_a_row_by_id_and_line(world):
    run_match(world)
    report = (world / "REPORT.md").read_text(encoding="utf-8")
    assert "| aphusem-2 | 3 | settlement | Aphüsem | Uphusum |" in report
