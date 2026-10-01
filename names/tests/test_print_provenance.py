"""names/provenance.py: the stamp tiles/build.sh writes into the archive's
metadata, printed for the files given."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import print_provenance, provenance


def test_the_tile_build_gets_the_same_stamp_as_the_search_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = {}
    for label in ("places.csv", "dialects.csv", "curation.csv", "dialect_areas.geojson"):
        inputs[label] = tmp_path / label
        inputs[label].write_text(label, encoding="utf-8")
    extracts = [{"file": "x.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}]
    objects = tmp_path / "osm_objects.json"
    objects.write_text(
        json.dumps({"built_from": {"extracts": extracts}, "objects": {}}), encoding="utf-8"
    )
    print_provenance.main(
        [
            "--names",
            str(inputs["places.csv"]),
            "--dialects",
            str(inputs["dialects.csv"]),
            "--curation",
            str(inputs["curation.csv"]),
            "--areas",
            str(inputs["dialect_areas.geojson"]),
            "--objects",
            str(objects),
        ]
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed == {
        "built_from": provenance.stamp(
            str(inputs["places.csv"]),
            str(inputs["dialects.csv"]),
            str(inputs["curation.csv"]),
            str(inputs["dialect_areas.geojson"]),
            str(objects),
        )
    }
    assert printed["built_from"]["extracts"] == extracts
    assert printed["built_from"]["places.csv"] == provenance.blob_hash(inputs["places.csv"])
