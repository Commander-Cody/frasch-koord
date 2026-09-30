"""The search index (web/public/data/names.json) names every entry by its
row's id, so a `?place=` link survives edits to the list and OSM id changes
alike (#23).  Its positions come from names/osm_objects.json, the file the
injector reads too, so a place is where its map label is (#24)."""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import pytest

from frasch import export_search_index
from frasch import paths as default_paths
from frasch import locate
from frasch.paths import StrPath
from frasch.placelist import OsmRef
from frasch.provenance import ExtractStamp
from frasch.searchindex import SearchEntry, SearchIndex
from conftest import curation_file, places_text

Rows = Iterable[Mapping[str, str]]
# the `export` fixture: `rows` exported -> {id: entry}
Export = Callable[[Rows], dict[str, SearchEntry]]

NAIBEL = {"id": "naibel", "kind": "settlement", "mooring": "Naibel", "de": "Niebüll",
          "osm": "node/240042766", "wikidata": "Q21003", "status": "ok"}
LUNGEDIK = {"id": "lungedik", "kind": "warft", "mooring": "Lungedik",
            "de": "Langerdeich", "osm": "way/28330569", "status": "ok"}
# the same dyke under a second name: two rows, one object
LUNGDIIK = LUNGEDIK | {"id": "lungdiik", "mooring": "Lungdiik"}
NORDWARW = {"id": "nordwarw", "kind": "warft", "mooring": "Nordwärw", "de": "Nordwarft",
            "osm": "way/1347936331; node/1332249790", "status": "ok"}
KRIS = {"id": "kris-nordfraschlonj", "kind": "landscape", "mooring": "Kris Nordfraschlönj",
        "nordgoes": "Noordfräischloun Krais", "de": "Kreis Nordfriesland",
        "osm": "relation/27019", "status": "ok"}
STIARDEBEL = {"id": "stiardebel", "kind": "settlement", "mooring": "Stiirdebel",
              "nordgoes": "Steerdebel", "suedgoes": "Stiardebel", "de": "Stadum",
              "osm": "node/2974350732", "status": "ok"}
RIPEN = {"id": "ripen", "kind": "settlement", "mooring": "Ripen", "de": "Ripen", "da": "Ribe",
         "osm": "node/597643755", "status": "auto"}
OBJECTS: dict[OsmRef, locate.LocatedObject] = {
    ("n", 240042766): {"lon": 8.83, "lat": 54.79, "name_nds": "Niböl"},
    ("w", 28330569): {"lon": 8.86, "lat": 54.47},
    ("w", 1347936331): {"lon": 8.84, "lat": 54.67},
    ("n", 1332249790): {"lon": 8.85, "lat": 54.68},
    ("r", 27019): {"lon": 8.84, "lat": 54.67, "admin_level": 6},
    # in the Südergoesharde strip of AREAS
    ("n", 2974350732): {"lon": 9.05, "lat": 54.72},
    ("n", 597643755): {"lon": 8.76, "lat": 55.33, "name": "Ribe"},
}
EXTRACTS: list[ExtractStamp] = [{"file": "schleswig-holstein-latest.osm.pbf",
             "replication_timestamp": "2026-09-22T20:22:59Z"}]


def box(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


AREAS = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"dialect": tag},
     "geometry": {"type": "Polygon", "coordinates": box(*bounds)}}
    for tag, bounds in [("frr-x-nordgoes", (8.78, 54.64, 9.00, 54.75)),
                        ("frr-x-suedgoes", (9.00, 54.64, 9.10, 54.75))]]}


@pytest.fixture
def paths(world: Path) -> Path:
    """The export's input files in `world`; `run(rows)` exports them."""
    (world / "osm_objects.json").write_text(
        locate.objects_json(locate.Objects(OBJECTS, {"extracts": EXTRACTS})),
        encoding="utf-8")
    (world / "areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    return world


def export_status(world: Path, rows: Rows) -> int:
    """Run the export command on `rows` -> its exit status."""
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    return export_search_index.main([
        "--names", str(world / "places.csv"),
        "--objects", str(world / "osm_objects.json"),
        "--curation", str(world / "curation.csv"),
        "--areas", str(world / "areas.geojson"),
        "--out", str(world / "names.json")])


def export_into(world: Path, rows: Rows) -> SearchIndex:
    assert export_status(world, rows) == 0
    index: SearchIndex = json.loads((world / "names.json").read_text(encoding="utf-8"))
    return index


@pytest.fixture
def export(paths: Path) -> Export:
    """Export `rows` -> {id: entry}."""
    def run(rows: Rows) -> dict[str, SearchEntry]:
        return {e["id"]: e for e in export_into(paths, rows)["places"]}
    return run


def test_an_entry_is_named_by_its_rows_id_and_keeps_its_osm_reference(
        export: Export) -> None:
    entries = export([NAIBEL])
    assert entries["naibel"]["osm"] == "node/240042766"
    assert (entries["naibel"]["lon"], entries["naibel"]["lat"]) == (8.83, 54.79)


def test_an_entry_is_where_the_first_object_of_its_row_is(export: Export) -> None:
    entries = export([NORDWARW])
    assert (entries["nordwarw"]["lon"], entries["nordwarw"]["lat"]) == (8.84, 54.67)


def test_two_rows_on_one_object_are_two_entries_by_id(export: Export) -> None:
    entries = export([LUNGEDIK, LUNGDIIK])
    assert sorted(entries) == ["lungdiik", "lungedik"]


def test_a_row_added_on_top_changes_no_other_entry(export: Export) -> None:
    # even one on the same object, which used to renumber `way/…#<line>`
    before = export([LUNGEDIK, LUNGDIIK, NAIBEL])
    after = export([LUNGEDIK | {"id": "lungdik", "mooring": "Lungdik"},
                    LUNGEDIK, LUNGDIIK, NAIBEL])
    assert after.pop("lungdik")
    assert after == before


def test_an_entry_gets_the_dialect_and_local_name_of_where_it_lies(export: Export) -> None:
    entries = export([STIARDEBEL])
    assert entries["stiardebel"]["dialect"] == "frr-x-suedgoes"
    assert entries["stiardebel"]["local"] == "Stiardebel"


def test_a_district_gets_no_dialect(export: Export) -> None:
    entries = export([KRIS])
    assert "dialect" not in entries["kris-nordfraschlonj"]
    assert "local" not in entries["kris-nordfraschlonj"]


def test_the_low_saxon_name_comes_from_the_object(export: Export) -> None:
    assert export([NAIBEL])["naibel"]["name_nds"] == "Niböl"


def test_the_generic_name_comes_from_the_object(export: Export) -> None:
    assert export([RIPEN])["ripen"]["name_osm"] == "Ribe"


def test_a_place_osm_does_not_have_gets_the_generic_name_of_its_map_point(
        paths: Path, export: Export) -> None:
    curation_file(paths, {"osm": "local/westerheide-amrum", "name": "Westerheide (Amrum)",
                          "lat": "54.65097", "lon": "8.34019"})
    waasterhias = {"id": "waasterhias", "kind": "settlement", "oomrang": "Waasterhias",
                   "de": "Westerheide", "osm": "local/westerheide-amrum", "status": "ok"}
    # the German name, as the injector names the point it adds (inject_names.point_tags)
    assert export([waasterhias])["waasterhias"]["name_osm"] == "Westerheide"


def test_a_row_whose_object_was_never_located_stops_the_export(
        paths: Path, capsys: pytest.CaptureFixture[str]) -> None:
    moved = NAIBEL | {"osm": "node/99"}
    assert export_status(paths, [moved]) == 1
    assert re.search(r"naibel.*node/99", capsys.readouterr().err)
    assert not (paths / "names.json").exists()


def test_a_row_keyed_by_wikidata_alone_is_left_out(export: Export) -> None:
    denmark = {"id": "danemark", "kind": "country", "mooring": "Dånemark",
               "de": "Dänemark", "wikidata": "Q35", "status": "auto"}
    assert "danemark" not in export([denmark, NAIBEL])


def git_hash(path: StrPath) -> str:
    return subprocess.run(["git", "hash-object", str(path)], capture_output=True,
                          text=True, check=True).stdout.strip()


def test_the_index_records_what_it_was_built_from(paths: Path) -> None:
    stamp = export_into(paths, [NAIBEL])["built_from"]
    assert stamp == {
        "places.csv": git_hash(paths / "places.csv"),
        "dialects.csv": git_hash(default_paths.DIALECTS),
        "curation.csv": git_hash(paths / "curation.csv"),
        "dialect_areas.geojson": git_hash(paths / "areas.geojson"),
        "osm_objects.json": git_hash(paths / "osm_objects.json"),
        "extracts": EXTRACTS,
    }
