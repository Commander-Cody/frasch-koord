"""What a generated file records about its inputs (#24): content hashes that
`git` would give the same file, so a stamp can be looked up in the history."""
from __future__ import annotations

import json

from frasch import provenance
from osm_fixture import write_extract


def test_a_file_hash_is_its_git_blob_hash(tmp_path):
    path = tmp_path / "places.csv"
    path.write_bytes(b"hello\n")
    # `printf 'hello\n' | git hash-object --stdin`
    assert provenance.blob_hash(path) == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_an_extract_is_named_by_its_file_and_replication_timestamp(tmp_path):
    pbf = write_extract(tmp_path / "denmark-latest.osm.pbf",
                        nodes={1: ((8.5, 55.0), {})},
                        timestamp="2026-09-22T20:22:59Z")
    assert provenance.extract_stamp(pbf) == {
        "file": "denmark-latest.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}


def test_an_extract_without_a_timestamp_says_so(tmp_path):
    pbf = write_extract(tmp_path / "x.osm.pbf", nodes={1: ((8.5, 55.0), {})})
    assert provenance.extract_stamp(pbf)["replication_timestamp"] == ""


def test_the_tile_build_gets_the_same_stamp_as_the_search_index(tmp_path, capsys):
    inputs = {}
    for label in ("places.csv", "dialects.csv", "curation.csv", "dialect_areas.geojson"):
        inputs[label] = tmp_path / label
        inputs[label].write_text(label, encoding="utf-8")
    extracts = [{"file": "x.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}]
    objects = tmp_path / "osm_objects.json"
    objects.write_text(json.dumps({"built_from": {"extracts": extracts}, "objects": {}}),
                       encoding="utf-8")
    provenance.main(["--names", str(inputs["places.csv"]),
                     "--dialects", str(inputs["dialects.csv"]),
                     "--curation", str(inputs["curation.csv"]),
                     "--areas", str(inputs["dialect_areas.geojson"]),
                     "--objects", str(objects)])
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"built_from": provenance.stamp(
        str(inputs["places.csv"]), str(inputs["dialects.csv"]), str(inputs["curation.csv"]),
        str(inputs["dialect_areas.geojson"]), str(objects))}
    assert printed["built_from"]["extracts"] == extracts
    assert printed["built_from"]["places.csv"] == provenance.blob_hash(inputs["places.csv"])
