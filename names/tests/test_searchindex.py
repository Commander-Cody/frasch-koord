"""The search index (web/public/data/names.json) names every entry by its
row's id, so a `?place=` link survives edits to the list and OSM id changes
alike (#23).  Its positions come from names/osm_objects.json, the file the
injector reads too, so a place is where its map label is (#24)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import pytest

from frasch import searchindex
from frasch.__main__ import main
from frasch.errors import PipelineError
from frasch.paths import StrPath
from frasch.objects import LocatedObject, Objects, objects_json
from frasch.refs import OsmRef
from frasch.provenance import ExtractStamp, Stamp
from frasch.placenames import SearchEntry
from frasch.searchindex import SearchIndex
from conftest import (
    REGISTRY,
    curation_file,
    path_options,
    places_text,
    schema_problems,
    workspace,
)

Rows = Iterable[Mapping[str, str]]
# the `export` fixture: `rows` exported -> {id: entry}
Export = Callable[[Rows], dict[str, SearchEntry]]

NAIBEL = {
    "id": "naibel",
    "kind": "settlement",
    "mooring": "Naibel",
    "de": "Niebüll",
    "osm": "node/240042766",
    "wikidata": "Q21003",
    "status": "ok",
}
LUNGEDIK = {
    "id": "lungedik",
    "kind": "warft",
    "mooring": "Lungedik",
    "de": "Langerdeich",
    "osm": "way/28330569",
    "status": "ok",
}
NORDWARW = {
    "id": "nordwarw",
    "kind": "warft",
    "mooring": "Nordwärw",
    "de": "Nordwarft",
    "osm": "way/1347936331; node/1332249790",
    "status": "ok",
}
KRIS = {
    "id": "kris-nordfraschlonj",
    "kind": "landscape",
    "mooring": "Kris Nordfraschlönj",
    "nordgoes": "Noordfräischloun Krais",
    "de": "Kreis Nordfriesland",
    "osm": "relation/27019",
    "status": "ok",
}
STIARDEBEL = {
    "id": "stiardebel",
    "kind": "settlement",
    "mooring": "Stiirdebel",
    "nordgoes": "Steerdebel",
    "suedgoes": "Stiardebel",
    "de": "Stadum",
    "osm": "node/2974350732",
    "status": "ok",
}
RIPEN = {
    "id": "ripen",
    "kind": "settlement",
    "mooring": "Ripen",
    "de": "Ripen",
    "da": "Ribe",
    "osm": "node/597643755",
    "status": "auto",
}
# a Mooring name only; the Hallig lies in the Nordergoesharde box of AREAS
HAMBORJER_HALI = {
    "id": "hamborjer-hali",
    "kind": "hallig",
    "mooring": "Hamborjer Håli",
    "de": "Hamburger Hallig",
    "osm": "relation/5615880",
    "status": "ok",
}
OBJECTS: dict[OsmRef, LocatedObject] = {
    ("n", 240042766): {"lon": 8.83, "lat": 54.79, "name_nds": "Niböl"},
    ("w", 28330569): {"lon": 8.86, "lat": 54.47},
    ("w", 1347936331): {"lon": 8.84, "lat": 54.67},
    ("n", 1332249790): {"lon": 8.85, "lat": 54.68},
    ("r", 27019): {"lon": 8.84, "lat": 54.67, "admin_level": 6},
    # in the Südergoesharde strip of AREAS
    ("n", 2974350732): {"lon": 9.05, "lat": 54.72},
    ("n", 597643755): {"lon": 8.76, "lat": 55.33, "name": "Ribe"},
    ("r", 5615880): {"lon": 8.84, "lat": 54.70, "admin_level": 10, "name_frr": "Hamborjer Hali"},
}
EXTRACTS: list[ExtractStamp] = [
    {"file": "schleswig-holstein-latest.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}
]


def box(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


AREAS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"dialect": tag},
            "geometry": {"type": "Polygon", "coordinates": box(*bounds)},
        }
        for tag, bounds in [
            ("frr-x-nordgoes", (8.78, 54.64, 9.00, 54.75)),
            ("frr-x-suedgoes", (9.00, 54.64, 9.10, 54.75)),
        ]
    ],
}


@pytest.fixture
def paths(world: Path) -> Path:
    """The export's input files in `world`; `run(rows)` exports them."""
    (world / "osm_objects.json").write_text(
        objects_json(Objects(OBJECTS, Stamp({}, EXTRACTS))), encoding="utf-8"
    )
    (world / "dialect_areas.geojson").write_text(json.dumps(AREAS), encoding="utf-8")
    return world


def export_into(world: Path, rows: Rows) -> SearchIndex:
    """Export the index of `rows` and read it back."""
    ws = workspace(world)
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")
    searchindex.run(ws, REGISTRY)
    index: SearchIndex = json.loads(Path(ws.index).read_text(encoding="utf-8"))
    return index


@pytest.fixture
def export(paths: Path) -> Export:
    """Export `rows` -> {id: entry}."""

    def run(rows: Rows) -> dict[str, SearchEntry]:
        return {e["id"]: e for e in export_into(paths, rows)["places"]}

    return run


def test_the_index_keeps_its_schema(paths: Path) -> None:
    # between them the rows have every field an entry can: a Low Saxon name
    # and a QID, a Danish and a generic name, a local name with its variety
    hali = HAMBORJER_HALI | {"local": "Hamborjer Hali (Foortuftinge)"}
    index = export_into(paths, [NAIBEL, RIPEN, hali])
    assert schema_problems(index, "search-index") == []


def test_an_entry_is_named_by_its_rows_id_and_keeps_its_osm_reference(export: Export) -> None:
    entries = export([NAIBEL])
    assert entries["naibel"]["osm"] == "node/240042766"
    assert (entries["naibel"]["lon"], entries["naibel"]["lat"]) == (8.83, 54.79)


def test_an_entry_is_where_the_first_object_of_its_row_is(export: Export) -> None:
    entries = export([NORDWARW])
    assert (entries["nordwarw"]["lon"], entries["nordwarw"]["lat"]) == (8.84, 54.67)


def test_a_row_added_on_top_changes_no_other_entry(export: Export) -> None:
    # an entry is keyed by its row's id, not by where the row stands
    before = export([LUNGEDIK, NAIBEL])
    after = export([NORDWARW, LUNGEDIK, NAIBEL])
    del after["nordwarw"]
    assert after == before


def test_an_entry_gets_the_dialect_and_local_name_of_where_it_lies(export: Export) -> None:
    entries = export([STIARDEBEL])
    assert entries["stiardebel"]["dialect"] == "frr-x-suedgoes"
    assert entries["stiardebel"]["local"] == "Stiardebel"


def test_the_local_name_of_a_row_without_one_is_osms_frisian_name(export: Export) -> None:
    # as the injector labels it (#81)
    assert export([HAMBORJER_HALI])["hamborjer-hali"]["local"] == "Hamborjer Hali"


def test_a_district_gets_no_dialect(export: Export) -> None:
    entries = export([KRIS])
    assert "dialect" not in entries["kris-nordfraschlonj"]
    assert "local" not in entries["kris-nordfraschlonj"]


def test_the_low_saxon_name_comes_from_the_object(export: Export) -> None:
    assert export([NAIBEL])["naibel"]["name_nds"] == "Niböl"


def test_the_generic_name_comes_from_the_object(export: Export) -> None:
    assert export([RIPEN])["ripen"]["name_osm"] == "Ribe"


def test_a_place_osm_does_not_have_gets_the_generic_name_of_its_map_point(
    paths: Path, export: Export
) -> None:
    curation_file(
        paths,
        {
            "osm": "local/westerheide-amrum",
            "name": "Westerheide (Amrum)",
            "lat": "54.65097",
            "lon": "8.34019",
        },
    )
    waasterhias = {
        "id": "waasterhias",
        "kind": "settlement",
        "oomrang": "Waasterhias",
        "de": "Westerheide",
        "osm": "local/westerheide-amrum",
        "status": "ok",
    }
    # the German name, as the injector names the point it adds (inject_names.point_tags)
    assert export([waasterhias])["waasterhias"]["name_osm"] == "Westerheide"


def test_a_row_whose_object_was_never_located_stops_the_export(paths: Path) -> None:
    moved = NAIBEL | {"osm": "node/99"}
    with pytest.raises(PipelineError, match=r"naibel.*node/99"):
        export_into(paths, [moved])
    assert not Path(workspace(paths).index).exists()


def test_an_object_that_was_never_asked_for_is_to_be_located(paths: Path) -> None:
    with pytest.raises(PipelineError, match="node/99 is not located yet .* `just rebuild objects`"):
        export_into(paths, [NAIBEL | {"osm": "node/99"}])


def test_an_object_no_extract_holds_is_a_matter_of_its_row(paths: Path) -> None:
    asked_in_vain = Objects(OBJECTS, Stamp({}, EXTRACTS), frozenset({("n", 99)}))
    (paths / "osm_objects.json").write_text(objects_json(asked_in_vain), encoding="utf-8")
    with pytest.raises(PipelineError, match="node/99 is in none of the extracts .* `osm` cell"):
        export_into(paths, [NAIBEL | {"osm": "node/99"}])


def test_a_row_keyed_by_wikidata_alone_is_left_out(export: Export) -> None:
    denmark = {
        "id": "danemark",
        "kind": "country",
        "mooring": "Dånemark",
        "de": "Dänemark",
        "wikidata": "Q35",
        "status": "auto",
    }
    assert "danemark" not in export([denmark, NAIBEL])


def git_hash(path: StrPath) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_the_index_records_what_it_was_built_from(paths: Path) -> None:
    stamp = export_into(paths, [NAIBEL])["built_from"]
    assert stamp == {
        "places.csv": git_hash(paths / "places.csv"),
        "dialects.csv": git_hash(paths / "dialects.csv"),
        "curation.csv": git_hash(paths / "curation.csv"),
        "dialect_areas.geojson": git_hash(paths / "dialect_areas.geojson"),
        "osm_objects.json": git_hash(paths / "osm_objects.json"),
        "extracts": EXTRACTS,
    }


def test_the_command_exports_the_index_of_the_workspace_its_options_name(
    paths: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace(paths)
    (paths / "places.csv").write_text(places_text([NAIBEL]), encoding="utf-8")
    files = path_options(ws, "names", "dialects", "curation", "areas", "objects", "index")
    assert main(["build", "index", *files]) == 0
    assert capsys.readouterr().out.startswith(f"wrote 1 entries to {ws.index}")
