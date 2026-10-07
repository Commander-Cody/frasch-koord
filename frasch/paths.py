"""Where the pipeline's files live -- in one place, so that a command's
default and the module that reads the file cannot disagree.  A `Workspace`
names every one of them; the commands work on `Workspace.default()`, the
checkout they run from, with single files replaced by their path options
(frasch.cli), and the tests on one of their own in a temp directory."""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass

# what a path parameter takes when the tests pass it a pathlib.Path
StrPath = str | os.PathLike[str]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# what a curation patch may hold: part of the code, not of a workspace
PATCH_SCHEMA = os.path.join(ROOT, "names", "curate-patch.schema.json")


@dataclass(frozen=True)
class Workspace:
    """The files of the pipeline, each by its path."""

    # the hand-edited inputs
    names: str  # the name list, places.csv
    dialects: str  # the dialect registry
    curation: str
    area_list: str  # which OSM objects make up each dialect's area
    # the committed build outputs
    areas: str  # one feature per dialect
    parts: str  # one per municipality, for the review overlay
    objects: str
    report: str
    index: str  # the search index of web/
    registry_json: str  # the registry as the frontend compiles it in
    # the git-ignored scratch files of matching and curation
    candidates: str
    matches: str
    wikidata_cache: str
    worklist: str
    patch: str
    lock: str  # held while a command rewrites the name list

    @classmethod
    def at(cls, root: StrPath) -> Workspace:
        """The files of a checkout at `root`."""
        names = os.path.join(root, "names")
        work = os.path.join(names, "work")
        web = os.path.join(root, "web")
        return cls(
            names=os.path.join(names, "places.csv"),
            dialects=os.path.join(names, "dialects.csv"),
            curation=os.path.join(names, "curation.csv"),
            area_list=os.path.join(names, "dialect_areas.csv"),
            areas=os.path.join(names, "dialect_areas.geojson"),
            parts=os.path.join(names, "dialect_areas_parts.geojson"),
            objects=os.path.join(names, "osm_objects.json"),
            report=os.path.join(names, "REPORT.md"),
            index=os.path.join(web, "public", "data", "names.json"),
            registry_json=os.path.join(web, "src", "generated", "dialects.json"),
            candidates=os.path.join(work, "candidates.jsonl"),
            matches=os.path.join(work, "matches.csv"),
            wikidata_cache=os.path.join(work, "wikidata-countries.json"),
            worklist=os.path.join(work, "curate.json"),
            patch=os.path.join(work, "curate-patch.jsonl"),
            lock=os.path.join(work, ".lock"),
        )

    @classmethod
    def default(cls) -> Workspace:
        """The files of the checkout this code runs from."""
        return cls.at(ROOT)

    def with_work(self, work: StrPath) -> Workspace:
        """This workspace with its scratch files in the directory `work`."""
        moved = {
            name: os.path.join(work, os.path.basename(getattr(self, name))) for name in SCRATCH
        }
        return dataclasses.replace(self, **moved)


# the scratch files of a workspace, by attribute
SCRATCH = (
    "candidates",
    "matches",
    "wikidata_cache",
    "worklist",
    "patch",
    "lock",
)
