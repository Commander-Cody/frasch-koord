"""names/update.py (`just update`): one command takes an edited name list, and
the decisions made in the curation view, to up-to-date outputs (#57)."""
from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from frasch import locate, paths, placelist, provenance, update
from frasch.provenance import ExtractStamp
from conftest import cand, places_text, write_candidates
from osm_fixture import ring, write_extract

AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"
# a village inside the Mooring area of the fixture extract
TOFTUM_NODE = ((8.83, 54.71), {"name": "Toftum", "place": "village"})
# a row the matcher finds in it, and one it does not
TOFTEM = {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"}
HESBEL = {"id": "hesbel", "kind": "settlement", "mooring": "Hesbel", "de": "Hesbüll"}


@pytest.fixture
def workspace(world: Path) -> Path:
    """`world` with the rest of the pipeline's inputs: the dialect registry,
    one dialect area, and an extract holding it and one village."""
    shutil.copy(paths.DIALECTS, world / "dialects.csv")
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    write_sh_extract(world)
    return world


def write_sh_extract(world: Path, timestamp: str = "2026-09-20T20:21:02Z") -> Path:
    nodes, way = ring(10, (8.7, 54.6), (8.9, 54.6), (8.9, 54.8), (8.7, 54.8))
    nodes[240044107] = TOFTUM_NODE
    return write_extract(world / "schleswig-holstein-latest.osm.pbf", nodes,
                         {5: (way, {})},
                         {1: ([("w", 5, "outer")], {"boundary": "administrative"})},
                         timestamp=timestamp)


def run(world: Path, *extra: str) -> int:
    """`update.main` on the files of `world`."""
    return update.main([
        str(world / "schleswig-holstein-latest.osm.pbf"), *extra,
        "--names", str(world / "places.csv"),
        "--dialects", str(world / "dialects.csv"),
        "--curation", str(world / "curation.csv"),
        "--area-list", str(world / "dialect_areas.csv"),
        "--areas", str(world / "dialect_areas.geojson"),
        "--parts", str(world / "dialect_areas_parts.geojson"),
        "--objects", str(world / "osm_objects.json"),
        "--index", str(world / "names.json"),
        "--registry-json", str(world / "dialects.json"),
        "--report", str(world / "REPORT.md"),
        "--work", str(world / "work"),
    ])


def write_places(world: Path, *rows: dict[str, str]) -> None:
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")


def read_places(world: Path) -> list[dict[str, str]]:
    with open(world / "places.csv", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_a_new_row_ends_up_matched_located_and_searchable(workspace: Path) -> None:
    write_places(workspace, TOFTEM | {"id": ""})
    assert run(workspace) == 0
    [row] = read_places(workspace)
    assert row["id"] == "toftem"
    assert (row["osm"], row["status"]) == ("node/240044107", "auto")
    objects = json.loads((workspace / "osm_objects.json").read_text(encoding="utf-8"))
    assert "node/240044107" in objects["objects"]
    index = json.loads((workspace / "names.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in index["places"]] == ["toftem"]


def test_a_decision_from_the_curation_view_is_written_into_the_name_list(
        workspace: Path) -> None:
    write_places(workspace, TOFTEM)
    patch = workspace / "work" / "curate-patch.jsonl"
    patch.write_text(json.dumps({"id": "toftem", "action": "osm",
                                 "osm": "node/240044107"}) + "\n", encoding="utf-8")
    assert run(workspace) == 0
    [row] = read_places(workspace)
    assert (row["osm"], row["status"]) == ("node/240044107", "ok")
    assert not patch.exists()


def test_rows_left_for_review_go_to_the_curation_worklist(workspace: Path) -> None:
    write_places(workspace, HESBEL)
    assert run(workspace) == 0
    worklist = json.loads((workspace / "work" / "curate.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in worklist["rows"]] == ["hesbel"]


def test_a_problem_in_the_name_list_stops_the_run_before_anything_is_built(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, {"kind": "settlement", "mooring": "Toftem (Karhiird",
                             "de": "Toftum"})
    assert run(workspace) == 1
    assert "unbalanced brackets" in capsys.readouterr().out
    assert sorted(p.name for p in workspace.iterdir()) == [
        "curation.csv", "dialect_areas.csv", "dialects.csv", "places.csv",
        "schleswig-holstein-latest.osm.pbf", "work"]
    assert not (workspace / "work" / "candidates.jsonl").exists()


def test_a_refused_curation_decision_does_not_stop_the_run(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM)
    patch = workspace / "work" / "curate-patch.jsonl"
    patch.write_text(json.dumps({"id": "deleted-row", "action": "skip"}) + "\n",
                     encoding="utf-8")
    assert run(workspace) == 1
    assert "deleted-row" in patch.read_text(encoding="utf-8")    # kept for the browser
    index = json.loads((workspace / "names.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in index["places"]] == ["toftem"]
    assert "refused" in capsys.readouterr().out


def test_a_curation_apply_that_cannot_run_stops_the_run(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM)
    (workspace / "work" / "curate-patch.jsonl").write_text(
        json.dumps({"id": "toftem", "action": "skip"}) + "\n", encoding="utf-8")
    with placelist.lock(str(workspace / "places.csv")):    # match.py is running
        assert run(workspace) == 1
    out = capsys.readouterr().out
    assert "update stopped: curation decisions failed" in out
    assert not (workspace / "names.json").exists()


def test_a_missing_extract_stops_the_run_with_how_to_get_it(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM)
    missing = workspace / "nowhere-latest.osm.pbf"
    assert run(workspace, "--area-extract", str(missing)) == 1
    assert f"{missing} not found" in capsys.readouterr().err
    assert not (workspace / "names.json").exists()


def test_a_second_run_on_the_same_extracts_skips_the_slow_steps(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM)
    assert run(workspace) == 0
    capsys.readouterr()
    assert run(workspace) == 0
    out = capsys.readouterr().out
    assert "== candidates: up to date" in out
    assert "== objects: up to date" in out
    assert "== areas: up to date" in out


def test_a_new_download_of_an_extract_rebuilds_the_candidates(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM)
    assert run(workspace) == 0
    write_sh_extract(workspace, timestamp="2026-09-30T20:21:02Z")
    capsys.readouterr()
    assert run(workspace) == 0
    out = capsys.readouterr().out
    assert "== candidates\n" in out
    assert "== objects\n" in out
    assert "== areas\n" in out


def test_the_run_ends_with_what_changed_and_what_is_left_to_curate(
        workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_places(workspace, TOFTEM,
                 HESBEL)
    assert run(workspace) == 0
    summary = capsys.readouterr().out.split("== summary\n")[1]
    changed = summary.split("left to curate")[0]
    for name in ("places.csv", "REPORT.md", "osm_objects.json", "dialect_areas.geojson",
                 "names.json", "dialects.json"):
        assert name in changed
    assert "curation.csv" not in changed
    assert "1 row left to curate" in summary
    assert "just tiles" in summary


# -------------------------------------------------------------- skip rules ---
SH: ExtractStamp = {"file": "schleswig-holstein-latest.osm.pbf",
                    "replication_timestamp": "2026-09-20T20:21:02Z"}
DK: ExtractStamp = {"file": "denmark-latest.osm.pbf",
                    "replication_timestamp": "2026-09-20T20:20:00Z"}
DK_REFRESHED: ExtractStamp = {"file": "denmark-latest.osm.pbf",
                              "replication_timestamp": "2026-09-30T20:20:00Z"}


def test_candidates_are_stale_until_built_from_the_current_extracts(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    assert update.candidates_stale(path, [SH, DK])
    write_candidates(path, {"header": {"extracts": [SH, DK]}})
    assert not update.candidates_stale(path, [SH, DK])
    assert update.candidates_stale(path, [SH])
    assert update.candidates_stale(path, [SH, DK_REFRESHED])


def test_candidates_without_a_header_are_stale(tmp_path: Path) -> None:
    path = write_candidates(tmp_path / "candidates.jsonl",
                            cand("n", 1, 8.83, 54.71, name="Toftum", place="village"))
    assert update.candidates_stale(path, [SH])


def test_objects_are_stale_until_located_for_the_current_references_and_extracts(
        tmp_path: Path) -> None:
    path = tmp_path / "osm_objects.json"
    assert update.objects_stale(path, {("n", 1)}, [SH])
    path.write_text(locate.objects_json(locate.Objects(
        {("n", 1): {"lon": 8.83, "lat": 54.71}}, {"extracts": [SH]})), encoding="utf-8")
    assert not update.objects_stale(path, {("n", 1)}, [SH])
    assert update.objects_stale(path, {("n", 1), ("w", 2)}, [SH])     # a new reference
    assert update.objects_stale(path, set(), [SH])                    # a row went
    assert update.objects_stale(path, {("n", 1)}, [SH, DK])


def write_area_files(paths: Sequence[Path], area_list: Path, registry: Path,
                     extract: ExtractStamp) -> None:
    """Dialect area files (no features) stamped as built from these inputs."""
    stamp = {"dialect_areas.csv": provenance.blob_hash(area_list),
             "dialects.csv": provenance.blob_hash(registry), "extracts": [extract]}
    for path in paths:
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [],
                                    "properties": {"built_from": stamp}}), encoding="utf-8")


def test_dialect_areas_are_stale_until_built_from_the_current_inputs(
        workspace: Path) -> None:
    area_list, registry = workspace / "dialect_areas.csv", workspace / "dialects.csv"
    outputs = [workspace / "dialect_areas.geojson", workspace / "dialect_areas_parts.geojson"]
    assert update.areas_stale(outputs, area_list, registry, [SH])
    write_area_files(outputs, area_list, registry, SH)
    assert not update.areas_stale(outputs, area_list, registry, [SH])
    assert update.areas_stale(outputs, area_list, registry, [DK])
    area_list.write_text(AREA_LIST + "frr-x-fering,Wyk,relation/2,\n", encoding="utf-8")
    assert update.areas_stale(outputs, area_list, registry, [SH])


def test_dialect_areas_are_stale_when_one_of_the_two_files_is(workspace: Path) -> None:
    area_list, registry = workspace / "dialect_areas.csv", workspace / "dialects.csv"
    outputs = [workspace / "dialect_areas.geojson", workspace / "dialect_areas_parts.geojson"]
    write_area_files(outputs[:1], area_list, registry, SH)
    assert update.areas_stale(outputs, area_list, registry, [SH])


def test_dialect_areas_without_a_stamp_are_stale(workspace: Path) -> None:
    area_list, registry = workspace / "dialect_areas.csv", workspace / "dialects.csv"
    outputs = [workspace / "dialect_areas.geojson", workspace / "dialect_areas_parts.geojson"]
    for path in outputs:
        path.write_text(json.dumps({"type": "FeatureCollection", "features": []}),
                        encoding="utf-8")
    assert update.areas_stale(outputs, area_list, registry, [SH])
