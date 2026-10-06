"""What a generated file records about its inputs (#24): content hashes that
`git` would give the same file, so a stamp can be looked up in the history."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from frasch import provenance
from frasch.__main__ import main
from frasch.errors import PipelineError
from frasch.paths import Workspace
from frasch.provenance import ExtractStamp, Stamp
from conftest import path_options


def test_a_file_hash_is_its_git_blob_hash(tmp_path: Path) -> None:
    path = tmp_path / "places.csv"
    path.write_bytes(b"hello\n")
    # `printf 'hello\n' | git hash-object --stdin`
    assert provenance.blob_hash(path) == "ce013625030ba8dba906f756967f9e9ca394464a"


EXTRACTS: list[ExtractStamp] = [
    {"file": "x.osm.pbf", "replication_timestamp": "2026-09-22T20:22:59Z"}
]
# `printf 'hello\n' | git hash-object --stdin`
HELLO = "ce013625030ba8dba906f756967f9e9ca394464a"


@pytest.fixture
def hello(tmp_path: Path) -> Path:
    path = tmp_path / "places.csv"
    path.write_bytes(b"hello\n")
    return path


def test_a_stamp_names_each_input_by_its_hash_and_the_extracts(hello: Path) -> None:
    stamp = Stamp.of({"places.csv": hello}, EXTRACTS)
    assert stamp.as_json() == {"places.csv": HELLO, "extracts": EXTRACTS}


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
    assert provenance.stamp(stamped).as_json() == {
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
    assert json.loads(capsys.readouterr().out) == {
        "built_from": provenance.stamp(stamped).as_json()
    }


BUILT_FROM = {"places.csv": HELLO, "extracts": EXTRACTS}
STAMP = Stamp({"places.csv": HELLO}, EXTRACTS)


def test_a_json_file_carries_its_stamp_at_the_top_level(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    path.write_text(json.dumps({"built_from": BUILT_FROM, "places": []}), encoding="utf-8")
    assert Stamp.read(path) == STAMP


def test_a_geojson_file_carries_its_stamp_in_its_properties(tmp_path: Path) -> None:
    path = tmp_path / "dialect_areas.geojson"
    collection = {"type": "FeatureCollection", "features": []}
    path.write_text(
        json.dumps(collection | {"properties": {"built_from": BUILT_FROM}}), encoding="utf-8"
    )
    assert Stamp.read(path) == STAMP


def test_a_json_lines_file_carries_its_stamp_as_its_header_line(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    path.write_text(
        json.dumps({"header": {"extracts": EXTRACTS}}) + '\n{"t": "n", "id": 1}\n', encoding="utf-8"
    )
    assert Stamp.read(path) == Stamp({}, EXTRACTS)


def test_a_markdown_file_carries_its_stamp_in_a_comment(tmp_path: Path) -> None:
    path = tmp_path / "REPORT.md"
    comment = '<!-- built_from: {"places.csv":"' + HELLO + '","extracts":[]} -->'
    path.write_text(f"# Name matching report\n\n{comment}\n", encoding="utf-8")
    assert Stamp.read(path) == Stamp({"places.csv": HELLO}, [])


def test_a_stamp_is_read_back_from_the_comment_it_writes(tmp_path: Path) -> None:
    path = tmp_path / "REPORT.md"
    path.write_text(f"# Name matching report\n{STAMP.as_comment()}\n", encoding="utf-8")
    assert Stamp.read(path) == STAMP


def test_a_file_without_a_stamp_has_none(tmp_path: Path) -> None:
    path = tmp_path / "dialect_areas.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    assert Stamp.read(path) is None


def test_a_missing_file_has_no_stamp(tmp_path: Path) -> None:
    assert Stamp.read(tmp_path / "osm_objects.json") is None


OTHER_HASH = "0" * 40
REFRESHED: list[ExtractStamp] = [
    {"file": "x.osm.pbf", "replication_timestamp": "2026-09-30T20:22:59Z"}
]


def test_a_stamp_differs_from_none_like_itself() -> None:
    assert STAMP.other_than(Stamp({"places.csv": HELLO}, EXTRACTS)) == []


def test_a_stamp_differs_in_an_input_of_another_content() -> None:
    assert STAMP.other_than(Stamp({"places.csv": OTHER_HASH}, EXTRACTS)) == ["places.csv"]


def test_a_stamp_differs_in_an_input_it_does_not_name() -> None:
    current = Stamp({"places.csv": HELLO, "dialects.csv": OTHER_HASH}, EXTRACTS)
    assert STAMP.other_than(current) == ["dialects.csv"]


def test_a_stamp_differs_in_the_extracts_of_another_download() -> None:
    assert STAMP.other_than(Stamp({"places.csv": HELLO}, REFRESHED)) == ["extracts"]


def test_extracts_that_are_not_at_hand_are_not_compared() -> None:
    assert STAMP.other_than(Stamp({"places.csv": HELLO}, None)) == []


def test_reading_a_stamp_needs_no_osm_library() -> None:
    # the search index and the matcher read stamps, and neither reads an extract
    loaded = "import sys, frasch.provenance; sys.exit('osmium' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", loaded]).returncode == 0


def test_an_objects_file_without_a_stamp_stops_the_stamp_with_how_to_rebuild_it(
    stamped: Workspace,
) -> None:
    Path(stamped.objects).write_text(json.dumps({"objects": {}}), encoding="utf-8")
    with pytest.raises(PipelineError, match="osm_objects.json .* `just rebuild objects`"):
        provenance.stamp(stamped)


def test_a_file_of_a_kind_that_carries_no_stamp_has_none(tmp_path: Path) -> None:
    # a path option may name any file: `frasch match --report notes.txt`
    path = tmp_path / "notes.txt"
    path.write_text(f"# Name matching report\n{STAMP.as_comment()}\n", encoding="utf-8")
    assert Stamp.read(path) is None
