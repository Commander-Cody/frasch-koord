"""The search index (web/public/data/names.json) names every entry by its
row's id, so a `?place=` link survives edits to the list and OSM id changes
alike (#23)."""
from __future__ import annotations

import csv
import json

import pytest

import export_search_index
import match
from conftest import places_text

NAIBEL = {"id": "naibel", "kind": "settlement", "mooring": "Naibel", "de": "Niebüll",
          "osm": "node/240042766", "wikidata": "Q21003", "status": "ok"}
LUNGEDIK = {"id": "lungedik", "kind": "warft", "mooring": "Lungedik",
            "de": "Langerdeich", "osm": "way/28330569", "status": "ok"}
# the same dyke under a second name: two rows, one object
LUNGDIIK = LUNGEDIK | {"id": "lungdiik", "mooring": "Lungdiik"}
NORDWARW = {"id": "nordwarw", "kind": "warft", "mooring": "Nordwärw", "de": "Nordwarft",
            "osm": "way/1347936331; node/1332249790", "status": "ok"}
# as match.py wrote them: an `osm` cell with several references may be spelled
# without the space the name list's convention has
POSITIONS = {"node/240042766": (8.83, 54.79), "way/28330569": (8.86, 54.47),
             "way/1347936331;node/1332249790": (8.84, 54.67)}


@pytest.fixture
def export(world):
    """Export `rows` (with the positions of POSITIONS) -> {id: entry}."""
    def run(rows):
        (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
        with open(world / "work" / "matches.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=match.MATCH_COLUMNS)
            w.writeheader()
            for osm, (lon, lat) in POSITIONS.items():
                w.writerow({"osm": osm, "lon": lon, "lat": lat})
        out = world / "names.json"
        export_search_index.main([
            "--names", str(world / "places.csv"),
            "--matches", str(world / "work" / "matches.csv"),
            "--curation", str(world / "curation.csv"),
            "--areas", str(world / "absent.geojson"),
            "--out", str(out), "--registry-out", str(world / "dialects.json")])
        return {e["id"]: e for e in json.loads(out.read_text(encoding="utf-8"))}
    return run


def test_an_entry_is_named_by_its_rows_id_and_keeps_its_osm_reference(export):
    entries = export([NAIBEL])
    assert entries["naibel"]["osm"] == "node/240042766"
    assert (entries["naibel"]["lon"], entries["naibel"]["lat"]) == (8.83, 54.79)


def test_a_position_is_found_however_the_references_are_spaced(export):
    entries = export([NORDWARW])
    assert (entries["nordwarw"]["lon"], entries["nordwarw"]["lat"]) == (8.84, 54.67)


def test_two_rows_on_one_object_are_two_entries_by_id(export):
    entries = export([LUNGEDIK, LUNGDIIK])
    assert sorted(entries) == ["lungdiik", "lungedik"]


def test_a_row_added_on_top_changes_no_other_entry(export):
    # even one on the same object, which used to renumber `way/…#<line>`
    before = export([LUNGEDIK, LUNGDIIK, NAIBEL])
    after = export([LUNGEDIK | {"id": "lungdik", "mooring": "Lungdik"},
                    LUNGEDIK, LUNGDIIK, NAIBEL])
    assert after.pop("lungdik")
    assert after == before
