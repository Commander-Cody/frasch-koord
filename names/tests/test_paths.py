"""frasch.paths: the one place that says where the pipeline's files live."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from frasch.paths import Workspace

REPO = Path(__file__).resolve().parents[2]


def relative(workspace: Workspace, root: Path) -> dict[str, str]:
    """Each file of the workspace, as its path below `root`."""
    return {
        name: os.path.relpath(path, root) for name, path in dataclasses.asdict(workspace).items()
    }


def test_a_workspace_lays_its_files_out_like_the_repository(tmp_path: Path) -> None:
    assert relative(Workspace.at(tmp_path), tmp_path) == {
        "names": "names/places.csv",
        "dialects": "names/dialects.csv",
        "curation": "names/curation.csv",
        "area_list": "names/dialect_areas.csv",
        "areas": "names/dialect_areas.geojson",
        "parts": "names/dialect_areas_parts.geojson",
        "objects": "names/osm_objects.json",
        "report": "names/REPORT.md",
        "index": "web/public/data/names.json",
        "registry_json": "web/src/generated/dialects.json",
        "candidates": "names/work/candidates.jsonl",
        "matches": "names/work/matches.csv",
        "wikidata_cache": "names/work/wikidata-countries.json",
        "extracts_state": "names/work/match-extracts.json",
        "worklist": "names/work/curate.json",
        "patch": "names/work/curate-patch.jsonl",
        "lock": "names/work/.lock",
    }


def test_the_default_workspace_is_the_checkout_the_code_runs_from() -> None:
    assert Workspace.default() == Workspace.at(REPO)


def test_another_work_directory_takes_the_scratch_files(tmp_path: Path) -> None:
    moved = Workspace.at(tmp_path).with_work(tmp_path / "scratch")
    assert relative(moved, tmp_path) == relative(Workspace.at(tmp_path), tmp_path) | {
        "candidates": "scratch/candidates.jsonl",
        "matches": "scratch/matches.csv",
        "wikidata_cache": "scratch/wikidata-countries.json",
        "extracts_state": "scratch/match-extracts.json",
        "worklist": "scratch/curate.json",
        "patch": "scratch/curate-patch.jsonl",
        "lock": "scratch/.lock",
    }
