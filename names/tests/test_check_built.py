"""names/check_built.py (`just check`, run in CI): are the committed build
outputs what their committed inputs give?  (#24: names.json was once built
from an uncommitted places.csv.)"""
from __future__ import annotations

import json
import shutil

import pytest

import build_dialect_areas
import check_built
import dialects
import export_search_index
import locate
import provenance
from conftest import places_text
from osm_fixture import ring, write_extract

NAIBEL = {"id": "naibel", "kind": "settlement", "mooring": "Naibel", "de": "Niebüll",
          "osm": "node/240042766", "status": "ok"}
AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"


@pytest.fixture
def repo(world):
    """A world whose outputs are all up to date; -> the check's argv."""
    (world / "places.csv").write_text(places_text([NAIBEL]), encoding="utf-8")
    shutil.copy(dialects.DEFAULT_PATH, world / "dialects.csv")
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    stamp = {"dialect_areas.csv": provenance.blob_hash(world / "dialect_areas.csv"),
             "dialects.csv": provenance.blob_hash(world / "dialects.csv"), "extracts": []}
    for name in ("dialect_areas.geojson", "dialect_areas_parts.geojson"):
        (world / name).write_text(json.dumps({"type": "FeatureCollection", "features": [],
                                              "properties": {"built_from": stamp}}),
                                  encoding="utf-8")
    (world / "osm_objects.json").write_text(locate.objects_json(locate.Objects(
        {("n", 240042766): {"lon": 8.83, "lat": 54.79}}, {"extracts": []})), encoding="utf-8")
    inputs = ["--names", str(world / "places.csv"), "--dialects", str(world / "dialects.csv"),
              "--curation", str(world / "curation.csv"),
              "--areas", str(world / "dialect_areas.geojson"),
              "--objects", str(world / "osm_objects.json")]
    export_search_index.main(inputs + ["--out", str(world / "names.json")])
    dialects.main(["--registry", str(world / "dialects.csv"),
                   "--export", str(world / "dialects.json")])
    return inputs + ["--index", str(world / "names.json"),
                     "--registry-json", str(world / "dialects.json"),
                     "--area-list", str(world / "dialect_areas.csv"),
                     "--parts", str(world / "dialect_areas_parts.geojson")]


def test_up_to_date_outputs_pass(repo):
    assert check_built.main(repo) == 0


def test_an_index_built_from_another_name_list_fails(repo, world, capsys):
    (world / "places.csv").write_text(places_text([NAIBEL | {"mooring": "Naibel;Niebel"}]),
                                      encoding="utf-8")
    assert check_built.main(repo) == 1
    assert "names.json" in capsys.readouterr().out


def test_a_registry_edit_without_an_export_fails(repo, world, capsys):
    with open(world / "dialects.csv", "a", encoding="utf-8") as fh:
        fh.write("frr-x-test,test,Test,living,no,\n")
    assert check_built.main(repo) == 1
    assert "dialects.json" in capsys.readouterr().out


def test_dialect_areas_built_from_another_area_list_fail(repo, world, capsys):
    (world / "dialect_areas.csv").write_text(AREA_LIST + "frr-x-fering,Wyk,relation/2,\n",
                                             encoding="utf-8")
    assert check_built.main(repo) == 1
    out = capsys.readouterr().out
    assert "dialect_areas.geojson" in out and "dialect_areas_parts.geojson" in out
    assert "just areas" in out


def test_a_row_whose_object_was_never_located_fails(repo, world, capsys):
    (world / "places.csv").write_text(places_text([NAIBEL | {"osm": "node/99"}]),
                                      encoding="utf-8")
    assert check_built.main(repo) == 1
    assert "node/99" in capsys.readouterr().out


# -------------------------------------------------------- --extracts (full) ---
@pytest.fixture
def extract(world, repo):
    """An extract the committed objects file and dialect areas were really
    built from; -> (argv with --extracts, the extract's nodes)."""
    nodes, way = ring(10, (8.8, 54.7), (8.9, 54.7), (8.9, 54.8), (8.8, 54.8))
    nodes[240042766] = ((8.83, 54.79), {})
    relations = {1: ([("w", 5, "outer")], {"boundary": "administrative"})}
    pbf = write_extract(world / "in.osm.pbf", nodes, {5: (way, {})}, relations)
    locate.main([str(pbf), "--names", str(world / "places.csv"),
                 "--out", str(world / "osm_objects.json")])
    build_dialect_areas.main([str(pbf), "--areas", str(world / "dialect_areas.csv"),
                              "--registry", str(world / "dialects.csv"),
                              "--out", str(world / "dialect_areas.geojson"),
                              "--parts-out", str(world / "dialect_areas_parts.geojson")])
    export_search_index.main(repo[:10] + ["--out", str(world / "names.json")])
    return repo + ["--extracts", str(pbf)], (nodes, way, relations)


def test_outputs_the_extract_really_gives_pass(extract):
    argv, _ = extract
    assert check_built.main(argv) == 0


def test_an_object_that_moved_in_the_extract_fails(extract, world, capsys):
    argv, (nodes, way, relations) = extract
    nodes[240042766] = ((8.84, 54.79), {})
    write_extract(world / "in.osm.pbf", nodes, {5: (way, {})}, relations)
    assert check_built.main(argv) == 1
    out = capsys.readouterr().out
    assert "osm_objects.json" in out and "just objects" in out
    assert "dialect_areas.geojson" not in out


def test_an_area_that_moved_in_the_extract_fails(extract, world, capsys):
    argv, (nodes, way, relations) = extract
    nodes[10] = ((8.7, 54.7), {})
    write_extract(world / "in.osm.pbf", nodes, {5: (way, {})}, relations)
    assert check_built.main(argv) == 1
    assert "dialect_areas.geojson" in capsys.readouterr().out


def test_each_file_is_rebuilt_from_the_extracts_its_stamp_names(extract, world):
    # the dialect areas come from the SH extract alone, the objects from SH + DK
    argv, _ = extract
    dk = write_extract(world / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    locate.main([argv[-1], str(dk), "--names", str(world / "places.csv"),
                 "--out", str(world / "osm_objects.json")])
    export_search_index.main(argv[:10] + ["--out", str(world / "names.json")])
    assert check_built.main(argv + [str(dk)]) == 0


def test_an_extract_a_stamp_names_must_be_given(extract, capsys):
    argv, _ = extract
    assert check_built.main(argv[:-1] + ["other.osm.pbf"]) == 1
    assert "in.osm.pbf" in capsys.readouterr().out
