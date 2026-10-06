"""What a generated file records about its inputs (#24): content hashes that
`git` would give the same file, so a stamp can be looked up in the history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frasch import provenance
from frasch.__main__ import main
from frasch.paths import Workspace
from conftest import path_options
from osm_fixture import write_extract


def test_a_file_hash_is_its_git_blob_hash(tmp_path: Path) -> None:
    path = tmp_path / "places.csv"
    path.write_bytes(b"hello\n")
    # `printf 'hello\n' | git hash-object --stdin`
    assert provenance.blob_hash(path) == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_an_extract_is_named_by_its_file_and_replication_timestamp(tmp_path: Path) -> None:
    pbf = write_extract(
        tmp_path / "denmark-latest.osm.pbf",
        nodes={1: ((8.5, 55.0), {})},
        timestamp="2026-09-22T20:22:59Z",
    )
    assert provenance.extract_stamp(pbf) == {
        "file": "denmark-latest.osm.pbf",
        "replication_timestamp": "2026-09-22T20:22:59Z",
    }


def test_an_extract_without_a_timestamp_says_so(tmp_path: Path) -> None:
    pbf = write_extract(tmp_path / "x.osm.pbf", nodes={1: ((8.5, 55.0), {})})
    assert provenance.extract_stamp(pbf)["replication_timestamp"] == ""


EXTRACTS = [{"file": "x.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}]


@pytest.fixture
def stamped(ws: Workspace) -> Workspace:
    """A workspace with the files the search index and the tiles are stamped
    with."""
    for path in (ws.names, ws.areas):
        Path(path).write_text(Path(path).name, encoding="utf-8")
    Path(ws.objects).write_text(
        json.dumps({"built_from": {"extracts": EXTRACTS}, "objects": {}}), encoding="utf-8"
    )
    return ws


def test_the_stamp_names_each_input_by_its_hash_and_the_extracts_of_the_objects(
    stamped: Workspace,
) -> None:
    assert provenance.stamp(stamped) == {
        "places.csv": provenance.blob_hash(stamped.names),
        "dialects.csv": provenance.blob_hash(stamped.dialects),
        "curation.csv": provenance.blob_hash(stamped.curation),
        "dialect_areas.geojson": provenance.blob_hash(stamped.areas),
        "osm_objects.json": provenance.blob_hash(stamped.objects),
        "extracts": EXTRACTS,
    }


def test_the_tile_build_gets_the_same_stamp_as_the_search_index(
    stamped: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    files = path_options(stamped, "names", "dialects", "curation", "areas", "objects")
    assert main(["provenance", *files]) == 0
    assert json.loads(capsys.readouterr().out) == {"built_from": provenance.stamp(stamped)}
