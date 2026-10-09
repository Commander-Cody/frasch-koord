"""`frasch update` (`just update`): one command takes an edited name list, and
the decisions made in the curation view, to up-to-date outputs (#57)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from frasch import dialects, placelist, update
from frasch.__main__ import main
from frasch.errors import PipelineError, Problem
from conftest import AREA_LIST, REGISTRY_CSV, TOFTUM_NODE, path_options, places_text
from conftest import workspace as workspace_of
from conftest import write_sh_extract

# a dialect the registry of the tests does not have
STRAND = "frr-x-strand,strand,Strander,extinct,no,\n"
# a row the matcher finds in the extract, and one it does not
TOFTEM = {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"}
HESBEL = {"id": "hesbel", "kind": "settlement", "mooring": "Hesbel", "de": "Hesbüll"}


@pytest.fixture
def workspace(pipeline_world: Path) -> Path:
    return pipeline_world


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


def test_a_run_without_an_extract_stops(workspace: Path) -> None:
    with pytest.raises(PipelineError, match="no OSM extract"):
        update.run(workspace_of(workspace), [])


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


def test_a_second_run_runs_the_matcher_again(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # it depends on Wikidata's answers too, which no stamp of its report covers
    write_places(workspace, TOFTEM)
    assert run(workspace) == 0
    capsys.readouterr()
    assert run(workspace) == 0
    assert "== report\n" in capsys.readouterr().out


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
    read_rows = dialects.rows
    reads = []

    def counted(path: str) -> tuple[list[dialects.Dialect], list[Problem]]:
        reads.append(path)
        return read_rows(path)

    monkeypatch.setattr(dialects, "rows", counted)
    assert run(workspace) == 0
    assert reads == [workspace_of(workspace).dialects]


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
