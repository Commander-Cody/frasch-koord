"""`frasch update` (`just update`): one command takes an edited name list, and
the decisions made in the curation view, to up-to-date outputs (#57)."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from frasch import build_dialect_areas, placelist, provenance, registry, update
from frasch.__main__ import main
from frasch.errors import PipelineError, Problem
from frasch.objects import Objects, objects_json
from frasch.provenance import ExtractStamp, Stamp
from conftest import REGISTRY_CSV, cand, path_options, places_text, write_candidates
from conftest import workspace as workspace_of
from osm_fixture import Nodes, ring, write_extract

AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"
# a dialect the registry of the tests does not have
STRAND = "frr-x-strand,strand,Strander,extinct,no,\n"
# a village inside the Mooring area of the fixture extract
TOFTUM_NODE = ((8.83, 54.71), {"name": "Toftum", "place": "village"})
# a row the matcher finds in it, and one it does not
TOFTEM = {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"}
HESBEL = {"id": "hesbel", "kind": "settlement", "mooring": "Hesbel", "de": "Hesbüll"}


@pytest.fixture
def workspace(world: Path) -> Path:
    """`world` with the rest of the pipeline's inputs: one dialect area, and
    an extract holding it and one village."""
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    write_sh_extract(world)
    return world


def write_sh_extract(
    world: Path, timestamp: str = "2026-09-20T20:21:02Z", more_nodes: Nodes | None = None
) -> Path:
    area, way = ring(10, (8.7, 54.6), (8.9, 54.6), (8.9, 54.8), (8.7, 54.8))
    nodes: Nodes = {**area, 240044107: TOFTUM_NODE, **(more_nodes or {})}
    return write_extract(
        world / "schleswig-holstein-latest.osm.pbf",
        nodes,
        {5: (way, {})},
        {1: ([("w", 5, "outer")], {"boundary": "administrative"})},
        timestamp=timestamp,
    )


def run(world: Path, area_extract: Path | None = None) -> int:
    """`update.run` on the workspace of `world` and its extract."""
    extract = str(world / "schleswig-holstein-latest.osm.pbf")
    return update.run(
        workspace_of(world), [extract], None if area_extract is None else str(area_extract)
    )


def index_file(world: Path) -> Path:
    return Path(workspace_of(world).index)


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
    index = json.loads(index_file(workspace).read_text(encoding="utf-8"))
    assert [e["id"] for e in index["places"]] == ["toftem"]


def test_the_objects_are_located_with_the_registry_passed_in(workspace: Path) -> None:
    # a row named only in a dialect of the workspace's own registry is on the map
    (workspace / "dialects.csv").write_text(REGISTRY_CSV + STRAND, encoding="utf-8")
    toftem = TOFTEM | {"mooring": "", "osm": "node/240044107", "status": "ok"}
    header, row, _ = places_text([toftem]).split("\n")
    (workspace / "places.csv").write_text(f"{header},strand\n{row},Toftem\n", encoding="utf-8")
    assert run(workspace) == 0
    objects = json.loads((workspace / "osm_objects.json").read_text(encoding="utf-8"))
    assert list(objects["objects"]) == ["node/240044107"]


def test_a_decision_from_the_curation_view_is_written_into_the_name_list(workspace: Path) -> None:
    write_places(workspace, TOFTEM)
    patch = workspace / "work" / "curate-patch.jsonl"
    patch.write_text(
        json.dumps({"id": "toftem", "action": "osm", "osm": "node/240044107"}) + "\n",
        encoding="utf-8",
    )
    assert run(workspace) == 0
    [row] = read_places(workspace)
    assert (row["osm"], row["status"]) == ("node/240044107", "ok")
    assert not patch.exists()


def test_rows_left_for_review_go_to_the_curation_worklist(workspace: Path) -> None:
    write_places(workspace, HESBEL)
    assert run(workspace) == 0
    worklist = json.loads((workspace / "work" / "curate.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in worklist["rows"]] == ["hesbel"]


def test_an_ambiguous_row_goes_to_the_curation_worklist_with_its_candidates(
    workspace: Path,
) -> None:
    # a second Toftum in North Frisia, 25 km from the first
    write_sh_extract(workspace, more_nodes={1: ((8.6, 54.5), TOFTUM_NODE[1])})
    write_places(workspace, TOFTEM)
    assert run(workspace) == 0
    worklist = json.loads((workspace / "work" / "curate.json").read_text(encoding="utf-8"))
    [row] = worklist["rows"]
    assert (row["id"], row["result"]) == ("toftem", "ambiguous")
    assert len(row["candidates"]) == 2


def test_a_problem_in_the_name_list_stops_the_run_before_anything_is_built(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, {"kind": "settlement", "mooring": "Toftem (Karhiird", "de": "Toftum"})
    assert run(workspace) == 1
    assert "unbalanced brackets" in capsys.readouterr().out
    assert sorted(p.name for p in workspace.iterdir()) == [
        "curation.csv",
        "dialect_areas.csv",
        "dialects.csv",
        "places.csv",
        "schleswig-holstein-latest.osm.pbf",
        "work",
    ]
    assert not (workspace / "work" / "candidates.jsonl").exists()


def test_a_refused_curation_decision_does_not_stop_the_run(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, TOFTEM)
    patch = workspace / "work" / "curate-patch.jsonl"
    patch.write_text(json.dumps({"id": "deleted-row", "action": "skip"}) + "\n", encoding="utf-8")
    assert run(workspace) == 1
    assert "deleted-row" in patch.read_text(encoding="utf-8")  # kept for the browser
    index = json.loads(index_file(workspace).read_text(encoding="utf-8"))
    assert [e["id"] for e in index["places"]] == ["toftem"]
    assert "refused" in capsys.readouterr().out


def test_a_curation_apply_that_cannot_run_stops_the_run(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, TOFTEM)
    (workspace / "work" / "curate-patch.jsonl").write_text(
        json.dumps({"id": "toftem", "action": "skip"}) + "\n", encoding="utf-8"
    )
    with placelist.lock(workspace_of(workspace).lock):  # the matcher is running
        assert run(workspace) == 1
    out = capsys.readouterr().out
    assert "update stopped: curation decisions failed" in out
    assert not index_file(workspace).exists()


def test_a_missing_extract_stops_the_run_with_how_to_get_it(workspace: Path) -> None:
    write_places(workspace, TOFTEM)
    missing = workspace / "nowhere-latest.osm.pbf"
    with pytest.raises(PipelineError, match=f"{missing} not found -- download it"):
        run(workspace, area_extract=missing)
    assert not index_file(workspace).exists()


def test_a_second_run_on_the_same_extracts_skips_the_slow_steps(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, TOFTEM)
    assert run(workspace) == 0
    capsys.readouterr()
    assert run(workspace) == 0
    out = capsys.readouterr().out
    assert "== candidates: up to date" in out
    assert "== objects: up to date" in out
    assert "== areas: up to date" in out


def test_a_new_download_of_an_extract_rebuilds_the_candidates(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, TOFTEM, HESBEL)
    assert run(workspace) == 0
    summary = capsys.readouterr().out.split("== summary\n")[1]
    changed = summary.split("left to curate")[0]
    for name in (
        "places.csv",
        "REPORT.md",
        "osm_objects.json",
        "dialect_areas.geojson",
        "names.json",
        "dialects.json",
    ):
        assert name in changed
    assert "curation.csv" not in changed
    assert "1 row left to curate" in summary
    assert "just tiles" in summary


def test_a_run_reads_the_dialect_registry_once(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_places(workspace, TOFTEM)
    read_rows = registry.rows
    reads = []

    def counted(path: str) -> tuple[list[registry.Dialect], list[Problem]]:
        reads.append(path)
        return read_rows(path)

    monkeypatch.setattr(registry, "rows", counted)
    assert run(workspace) == 0
    assert reads == [workspace_of(workspace).dialects]


# -------------------------------------------------------------- skip rules ---
SH: ExtractStamp = {
    "file": "schleswig-holstein-latest.osm.pbf",
    "replication_timestamp": "2026-09-20T20:21:02Z",
}
DK: ExtractStamp = {
    "file": "denmark-latest.osm.pbf",
    "replication_timestamp": "2026-09-20T20:20:00Z",
}
DK_REFRESHED: ExtractStamp = {
    "file": "denmark-latest.osm.pbf",
    "replication_timestamp": "2026-09-30T20:20:00Z",
}


def test_candidates_are_stale_until_built_from_the_current_extracts(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    assert update.candidates_stale(path, [SH, DK])
    write_candidates(path, {"header": {"extracts": [SH, DK]}})
    assert not update.candidates_stale(path, [SH, DK])
    assert update.candidates_stale(path, [SH])
    assert update.candidates_stale(path, [SH, DK_REFRESHED])


def test_candidates_without_a_header_are_stale(tmp_path: Path) -> None:
    path = write_candidates(
        tmp_path / "candidates.jsonl", cand("n", 1, 8.83, 54.71, name="Toftum", place="village")
    )
    assert update.candidates_stale(path, [SH])


def test_objects_are_stale_until_located_for_the_current_references_and_extracts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "osm_objects.json"
    assert update.objects_stale(path, {("n", 1)}, [SH])
    path.write_text(
        objects_json(Objects({("n", 1): {"lon": 8.83, "lat": 54.71}}, Stamp({}, [SH]))),
        encoding="utf-8",
    )
    assert not update.objects_stale(path, {("n", 1)}, [SH])
    assert update.objects_stale(path, {("n", 1), ("w", 2)}, [SH])  # a new reference
    assert update.objects_stale(path, set(), [SH])  # a row went
    assert update.objects_stale(path, {("n", 1)}, [SH, DK])


def write_area_files(
    paths: Sequence[Path], area_list: Path, registry: Path, extract: ExtractStamp
) -> None:
    """Dialect area files (no features) stamped as built from these inputs."""
    stamp = {
        "dialect_areas.csv": provenance.blob_hash(area_list),
        "dialects.csv": provenance.blob_hash(registry),
        "extracts": [extract],
    }
    for path in paths:
        path.write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": [], "properties": {"built_from": stamp}}
            ),
            encoding="utf-8",
        )


def test_dialect_areas_are_stale_until_built_from_the_current_inputs(workspace: Path) -> None:
    ws = workspace_of(workspace)
    area_list, outputs = Path(ws.area_list), [Path(ws.areas), Path(ws.parts)]
    assert update.areas_stale(ws, [SH])
    write_area_files(outputs, area_list, Path(ws.dialects), SH)
    assert not update.areas_stale(ws, [SH])
    assert update.areas_stale(ws, [DK])
    area_list.write_text(AREA_LIST + "frr-x-fering,Wyk,relation/2,\n", encoding="utf-8")
    assert update.areas_stale(ws, [SH])


def test_dialect_areas_are_stale_after_a_registry_edit(workspace: Path) -> None:
    ws = workspace_of(workspace)
    extract = workspace / "schleswig-holstein-latest.osm.pbf"
    build_dialect_areas.run(ws, registry.read(ws.dialects), [extract])
    assert not update.areas_stale(ws, [SH])
    dialects_csv = Path(ws.dialects)
    text = dialects_csv.read_text(encoding="utf-8")
    dialects_csv.write_text(text.replace(",Mooring,", ",Mooring (edited),", 1), encoding="utf-8")
    assert update.areas_stale(ws, [SH])


def test_dialect_areas_are_stale_when_one_of_the_two_files_is(workspace: Path) -> None:
    ws = workspace_of(workspace)
    write_area_files([Path(ws.areas)], Path(ws.area_list), Path(ws.dialects), SH)
    assert update.areas_stale(ws, [SH])


def test_dialect_areas_without_a_stamp_are_stale(workspace: Path) -> None:
    ws = workspace_of(workspace)
    for path in (ws.areas, ws.parts):
        Path(path).write_text(
            json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
        )
    assert update.areas_stale(ws, [SH])


# ------------------------------------------------------------- the command ---
# every path option of the command, for a workspace
FILES = ["names", "curation", "area_list", "areas", "parts", "objects", "index"]
FILES += ["registry_json", "report", "work"]


def test_the_command_fails_on_a_missing_extract_and_says_how_to_get_it(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_places(workspace, TOFTEM)
    ws = workspace_of(workspace)
    missing = str(workspace / "nowhere-latest.osm.pbf")
    assert main(["update", missing, *path_options(ws, *FILES, "dialects")]) == 1
    assert capsys.readouterr().err == f"{missing} not found -- download it with `just extracts`\n"


@pytest.fixture
def another_registry(workspace: Path, tmp_path: Path) -> Path:
    """`frasch update --dialects X` on a workspace only X can read: X has a
    dialect of its own, which the dialect area is assigned to and the name
    list names its rows in -- one the matcher finds, one decided in the
    curation view, one left for review.  -> the workspace's names/."""
    other = tmp_path / "other-dialects.csv"
    other.write_text(REGISTRY_CSV + STRAND, encoding="utf-8")
    (workspace / "dialect_areas.csv").write_text(
        AREA_LIST.replace("frr-x-mooring", "frr-x-strand"), encoding="utf-8"
    )
    rows = [TOFTEM, HESBEL, HESBEL | {"id": "hesbel-2"}]
    header, *lines = places_text([row | {"mooring": ""} for row in rows]).splitlines()
    named = [f"{line},{row['mooring']}" for line, row in zip(lines, rows, strict=True)]
    (workspace / "places.csv").write_text(
        "\n".join([f"{header},strand", *named]) + "\n", encoding="utf-8"
    )
    (workspace / "work" / "curate-patch.jsonl").write_text(
        json.dumps({"id": "hesbel-2", "action": "skip"}) + "\n", encoding="utf-8"
    )
    extract = str(workspace / "schleswig-holstein-latest.osm.pbf")
    files = path_options(workspace_of(workspace), *FILES)
    assert main(["update", extract, *files, "--dialects", str(other)]) == 0
    return workspace


def test_the_registry_of_the_dialects_option_reads_the_list_for_the_curation_decisions(
    another_registry: Path,
) -> None:
    assert {r["id"]: r["status"] for r in read_places(another_registry)}["hesbel-2"] == "skip"


def test_the_registry_of_the_dialects_option_names_the_rows_the_matcher_fills(
    another_registry: Path,
) -> None:
    assert {r["id"]: r["osm"] for r in read_places(another_registry)}["toftem"] == (
        "node/240044107"
    )


def test_the_registry_of_the_dialects_option_decides_which_objects_are_located(
    another_registry: Path,
) -> None:
    objects = json.loads((another_registry / "osm_objects.json").read_text(encoding="utf-8"))
    assert list(objects["objects"]) == ["node/240044107"]


def test_the_registry_of_the_dialects_option_assigns_the_dialect_areas(
    another_registry: Path,
) -> None:
    areas = json.loads((another_registry / "dialect_areas.geojson").read_text(encoding="utf-8"))
    assert [f["properties"]["dialect"] for f in areas["features"]] == ["frr-x-strand"]


def test_the_registry_of_the_dialects_option_is_the_one_exported_for_the_frontend(
    another_registry: Path,
) -> None:
    exported = Path(workspace_of(another_registry).registry_json).read_text(encoding="utf-8")
    assert '"tag":"frr-x-strand"' in exported


def test_the_registry_of_the_dialects_option_names_the_entries_of_the_search_index(
    another_registry: Path,
) -> None:
    index = json.loads(index_file(another_registry).read_text(encoding="utf-8"))
    assert [e["names"] for e in index["places"]] == [{"frr-x-strand": "Toftem"}]


def test_the_registry_of_the_dialects_option_names_the_rows_of_the_curation_worklist(
    another_registry: Path,
) -> None:
    worklist = json.loads((another_registry / "work" / "curate.json").read_text(encoding="utf-8"))
    assert [(r["id"], r["names"]) for r in worklist["rows"]] == [("hesbel", {"strand": "Hesbel"})]
