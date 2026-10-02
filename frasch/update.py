#!/usr/bin/env python3
"""Bring every file the name list feeds up to date, in one run (`just update`).

    names/update.py <in.osm.pbf> [<in.osm.pbf> ...] [--area-extract <pbf>]

After an edit to places.csv, or a session in the curation view (`?curate`),
this runs the pipeline's commands in their order:

  ids and checks      give new rows an `id`, check the hand-edited files
  curation decisions  `curate.py apply`, when the view left a patch
  candidates          `build_candidates.py`          -- only when stale
  match               fill the empty `osm` cells of places.csv, REPORT.md
  objects             `locate.py`, osm_objects.json   -- only when stale
  areas               `build_dialect_areas.py`        -- only when stale
  dialect registry    web/src/generated/dialects.json
  search index        web/public/data/names.json
  curation worklist   `curate.py export`: what is left for the view
  check               the committed outputs match their inputs (`just check-outputs`)

and ends with the files it changed and the rows left to curate.  The slow
steps are skipped when their output was built from what is there now (see
`candidates_stale`, `objects_stale`, `areas_stale`).  A step that fails
stops the run.  A decision `apply` refuses does not: it stays in the patch,
the rest of the run goes on, and the run exits 1 at its end.

The tiles are not built (`just tiles`), and nothing is committed: review the
result with `git diff`.
"""

from __future__ import annotations

import argparse
import enum
import json
import os
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from frasch import (
    build_candidates,
    build_dialect_areas,
    candidates,
    check,
    check_built,
    cli,
    curate,
    export_dialects,
    export_search_index,
    locate,
    match,
    paths,
    placelist,
    provenance,
    registry,
)
from frasch.errors import PipelineError
from frasch.objects import read_objects
from frasch.paths import StrPath
from frasch.placelist import OsmRef
from frasch.provenance import ExtractStamp


class Outcome(enum.Enum):
    DONE = "done"
    WARNED = "done, with something to look at"  # the run goes on, but exits 1
    FAILED = "failed"  # the run stops


def always() -> bool:
    return True


@dataclass(frozen=True)
class Step:
    """One step of the run; it is skipped (saying `skipped`) when `needed`
    says so at the moment it is due."""

    name: str
    run: Callable[[], Outcome]
    needed: Callable[[], bool] = always
    skipped: str = "up to date"


def command(main: cli.Command, *argv: str) -> Callable[[], Outcome]:
    """A command as a step: any exit status but 0 stops the run."""
    return lambda: Outcome.DONE if main(argv) == 0 else Outcome.FAILED


def apply_decisions(names: str, curation: str, patch: str) -> Outcome:
    """`curate.py apply`: a decision it refuses stays in the patch, for the
    browser to show and the curator to fix -- no reason to hold back the rest
    of the run.  A problem that stops the apply itself stops the run."""
    try:
        refused = curate.apply(names, curation, patch)
    except PipelineError as stop:
        print(stop, file=sys.stderr)
        return Outcome.FAILED
    return Outcome.WARNED if refused else Outcome.DONE


def candidates_stale(path: StrPath, extracts: list[ExtractStamp]) -> bool:
    """Are the candidates missing, or built from other extracts than
    `extracts` (another set, or another download of one)?  The scan takes
    minutes; a name list edit alone never needs it."""
    return not os.path.exists(path) or candidates.read_header(path) != extracts


def objects_stale(path: StrPath, refs: Collection[OsmRef], extracts: list[ExtractStamp]) -> bool:
    """Is the objects file missing, or does it hold other references than
    `refs` (the rows on the map), or come from other extracts?  An object
    only moves when the extract does."""
    if not os.path.exists(path):
        return True
    objects = read_objects(os.fspath(path))
    return set(objects.by_ref) != set(refs) or objects.built_from["extracts"] != extracts


def areas_stale(
    outputs: Sequence[StrPath],
    area_list: StrPath,
    registry_csv: StrPath,
    extracts: list[ExtractStamp],
) -> bool:
    """Is either dialect area file missing, or built from another area list,
    registry or extract than these?"""
    current = build_dialect_areas.stamp(area_list, registry_csv, extracts)
    return any(not os.path.exists(path) or provenance.recorded(path) != current for path in outputs)


def mapped_refs(names: str, dialects: str) -> set[OsmRef]:
    """The OSM references of the rows on the map, as the name list has them now."""
    reg = registry.read(dialects)
    rows, _ = placelist.read(names, reg)
    return locate.mapped_refs(rows, reg)


def steps(a: argparse.Namespace) -> list[Step]:
    """The run's steps, in order."""
    extracts = [provenance.extract_stamp(p) for p in a.extracts]
    area_extract = provenance.extract_stamp(a.area_extract)
    inputs = [
        "--names",
        a.names,
        "--dialects",
        a.dialects,
        "--curation",
        a.curation,
        "--areas",
        a.areas,
        "--objects",
        a.objects,
    ]
    return [
        Step(
            "ids and checks",
            command(
                check.main,
                "--fix",
                "--names",
                a.names,
                "--curation",
                a.curation,
                "--dialects",
                a.dialects,
                "--areas",
                a.area_list,
            ),
        ),
        Step(
            "curation decisions",
            lambda: apply_decisions(a.names, a.curation, a.patch),
            needed=lambda: os.path.exists(a.patch),
            skipped="none made",
        ),
        Step(
            "candidates",
            command(build_candidates.main, *a.extracts, "--out", a.candidates),
            needed=lambda: candidates_stale(a.candidates, extracts),
        ),
        Step(
            "match",
            command(
                match.main,
                "--names",
                a.names,
                "--candidates",
                a.candidates,
                "--matches",
                a.matches,
                "--report",
                a.report,
                "--wikidata-cache",
                a.wikidata_cache,
            ),
        ),
        Step(
            "objects",
            command(
                locate.main,
                *a.extracts,
                "--names",
                a.names,
                "--dialects",
                a.dialects,
                "--out",
                a.objects,
            ),
            needed=lambda: objects_stale(a.objects, mapped_refs(a.names, a.dialects), extracts),
        ),
        Step(
            "areas",
            command(
                build_dialect_areas.main,
                a.area_extract,
                "--areas",
                a.area_list,
                "--registry",
                a.dialects,
                "--out",
                a.areas,
                "--parts-out",
                a.parts,
            ),
            needed=lambda: areas_stale([a.areas, a.parts], a.area_list, a.dialects, [area_extract]),
        ),
        Step(
            "dialect registry",
            command(export_dialects.main, "--registry", a.dialects, "--export", a.registry_json),
        ),
        Step("search index", command(export_search_index.main, *inputs, "--out", a.index)),
        Step(
            "curation worklist",
            command(
                curate.main,
                "export",
                "--names",
                a.names,
                "--matches",
                a.matches,
                "--candidates",
                a.candidates,
                "--out",
                a.worklist,
            ),
        ),
        Step(
            "check",
            command(
                check_built.main,
                *inputs,
                "--index",
                a.index,
                "--registry-json",
                a.registry_json,
                "--area-list",
                a.area_list,
                "--parts",
                a.parts,
            ),
        ),
    ]


def outputs(a: argparse.Namespace) -> list[str]:
    """The files of the repository a run may change."""
    return [a.names, a.curation, a.report, a.objects, a.areas, a.parts, a.index, a.registry_json]


def contents(files: Sequence[str]) -> dict[str, str | None]:
    """Each file's blob hash, None when it does not exist."""
    return {f: provenance.blob_hash(f) if os.path.exists(f) else None for f in files}


def summary(before: Mapping[str, str | None], worklist: str) -> str:
    """What the run changed (`before`: `contents` at its start) and what is
    left for the curator."""
    changed = [os.path.relpath(f) for f, was in before.items() if contents([f])[f] != was]
    with open(worklist, encoding="utf-8") as fh:
        left = len(json.load(fh)["rows"])
    return "\n".join(
        [
            f"changed: {', '.join(changed)}" if changed else "nothing changed",
            f"{left} row{'' if left == 1 else 's'} left to curate: `npm run dev` in web/, "
            f"then open /?curate",
            "review with `git diff`; to see the labels on the map, build the tiles "
            "with `just tiles`",
        ]
    )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "extracts", nargs="+", metavar="PBF", help="the OSM extracts the name list's objects are in"
    )
    ap.add_argument(
        "--area-extract",
        metavar="PBF",
        help="the extract the dialect areas are built from (default: the first of the extracts)",
    )
    ap.add_argument("--names", default=paths.PLACES)
    ap.add_argument("--dialects", default=paths.DIALECTS)
    ap.add_argument("--curation", default=paths.CURATION)
    ap.add_argument("--area-list", default=paths.DIALECT_AREA_LIST)
    ap.add_argument("--areas", default=paths.DIALECT_AREAS)
    ap.add_argument("--parts", default=paths.DIALECT_AREA_PARTS)
    ap.add_argument("--objects", default=paths.OBJECTS)
    ap.add_argument("--index", default=paths.SEARCH_INDEX)
    ap.add_argument("--registry-json", default=paths.REGISTRY_JSON)
    ap.add_argument("--report", default=paths.REPORT)
    ap.add_argument(
        "--work",
        default=paths.WORK,
        help="the git-ignored scratch directory of matching and curation",
    )
    a = ap.parse_args(argv)
    a.area_extract = a.area_extract or a.extracts[0]
    missing = [p for p in dict.fromkeys([*a.extracts, a.area_extract]) if not os.path.exists(p)]
    if missing:
        raise PipelineError(f"{', '.join(missing)} not found -- download it with `just extracts`")
    a.candidates, a.matches, a.worklist, a.patch, a.wikidata_cache = (
        os.path.join(a.work, os.path.basename(default))
        for default in (
            paths.CANDIDATES,
            paths.MATCHES,
            paths.WORKLIST,
            paths.PATCH,
            paths.WIKIDATA_CACHE,
        )
    )
    return a


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    a = parse_args(argv)
    before = contents(outputs(a))
    warned = []
    for step in steps(a):
        if not step.needed():
            print(f"== {step.name}: {step.skipped}")
            continue
        print(f"== {step.name}", flush=True)
        outcome = step.run()
        if outcome is Outcome.FAILED:
            print(f"update stopped: {step.name} failed")
            return 1
        if outcome is Outcome.WARNED:
            warned.append(step.name)
    print("== summary")
    print(summary(before, a.worklist))
    if warned:
        print(f"update done, but look at the output of: {', '.join(warned)}")
        return 1
    return 0
