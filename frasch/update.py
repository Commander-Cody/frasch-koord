"""Bring every file the name list feeds up to date, in one run (`just update`).

    frasch update <in.osm.pbf> [<in.osm.pbf> ...] [--area-extract <pbf>]

After an edit to places.csv, or a session in the curation view (`?curate`),
this runs the pipeline's commands in their order:

  ids and input check `check-inputs --fix`: give new rows an `id`, check the
                      hand-edited files
  curation decisions  `curate apply`, when the view left a patch
  candidates          `candidates`                   -- only when stale
  match               fill the empty `osm` cells of places.csv, REPORT.md
  objects             `objects`, osm_objects.json     -- only when stale
  areas               `areas`                         -- only when stale
  dialect registry    web/src/generated/dialects.json
  search index        web/public/data/names.json
  curation worklist   `curate export`: what is left for the view
  output check        `check-outputs`: the committed outputs match their inputs

and ends with the files it changed and the rows left to curate.  The slow
steps are skipped when their output was built from what is there now (see
`candidates_stale`, `objects_stale`, `areas_stale`).  A step that fails
stops the run.  A decision `apply` refuses does not: it stays in the patch,
the rest of the run goes on, and the run exits 1 at its end.

Every step works on the same workspace, and on the dialect registry as the
first step read and checked it.

The tiles are not built (`just tiles`), and nothing is committed: review the
result with `git diff`.
"""

from __future__ import annotations

import enum
import json
import os
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from frasch import (
    build_candidates,
    build_dialect_areas,
    check_inputs,
    check_outputs,
    cli,
    curate,
    locate,
    match,
    osmscan,
    provenance,
    registry,
    searchindex,
)
from frasch.errors import PipelineError
from frasch.objects import read_objects
from frasch.paths import StrPath, Workspace
from frasch.placelist import OsmRef
from frasch.provenance import ExtractStamp, Stamp
from frasch.registry import Registry


class Outcome(enum.Enum):
    DONE = "done"
    WARNED = "done, with something to look at"  # the run goes on, but exits 1
    FAILED = "failed"  # the run stops


def always() -> bool:
    return True


@dataclass(frozen=True)
class Step:
    """One step of the run; it is skipped (saying `skipped`) when `needed`
    says so at the moment it is due.  A PipelineError it raises fails it."""

    name: str
    run: Callable[[], Outcome]
    needed: Callable[[], bool] = always
    skipped: str = "up to date"


def done(run: Callable[[], object]) -> Callable[[], Outcome]:
    """A step that is done once `run` returns."""

    def step() -> Outcome:
        run()
        return Outcome.DONE

    return step


def unless(failed: Callable[[], object], otherwise: Outcome) -> Callable[[], Outcome]:
    """A step that takes the outcome `otherwise` when `failed` returns
    something true -- an exit status, problems, refused decisions."""
    return lambda: otherwise if failed() else Outcome.DONE


def candidates_stale(path: StrPath, extracts: list[ExtractStamp]) -> bool:
    """Are the candidates missing, or built from other extracts than
    `extracts` (another set, or another download of one)?  The scan takes
    minutes; a name list edit alone never needs it."""
    found = Stamp.read(path)
    return found is None or found.extracts != extracts


def objects_stale(path: StrPath, refs: Collection[OsmRef], extracts: list[ExtractStamp]) -> bool:
    """Is the objects file missing, or does it hold other references than
    `refs` (the rows on the map), or come from other extracts?  An object
    only moves when the extract does."""
    if not os.path.exists(path):
        return True
    objects = read_objects(os.fspath(path))
    return set(objects.by_ref) != set(refs) or objects.stamp.extracts != extracts


def areas_stale(ws: Workspace, extracts: list[ExtractStamp]) -> bool:
    """Is either dialect area file missing, or built from another area list,
    registry or extract than the workspace's and `extracts`?"""
    current = build_dialect_areas.stamp(ws, extracts)
    return any(Stamp.read(path) != current for path in (ws.areas, ws.parts))


@dataclass
class Inputs:
    """What a run works on: its workspace and extracts, and the dialect
    registry once the first step has read and checked it -- the file is read
    that once, and every later step works on the same registry."""

    ws: Workspace
    extracts: Sequence[str]
    area_extract: str
    checked: Registry | None = None

    @property
    def reg(self) -> Registry:
        if self.checked is None:
            raise RuntimeError("the dialect registry is asked for before the input check has run")
        return self.checked

    def check(self) -> Outcome:
        """The first step: give new rows an id and check the hand-edited files."""
        found = check_inputs.run(self.ws, fix=True)
        self.checked = found.registry
        return Outcome.FAILED if found.problems else Outcome.DONE


def steps(inputs: Inputs) -> list[Step]:
    """The run's steps, in order."""
    ws, extracts, area_extract = inputs.ws, inputs.extracts, inputs.area_extract
    stamps = osmscan.extract_stamps(extracts)
    area_stamps = osmscan.extract_stamps([area_extract])
    return [
        Step("ids and input check", inputs.check),
        Step(
            "curation decisions",
            unless(lambda: curate.apply(ws, inputs.reg), Outcome.WARNED),
            needed=lambda: os.path.exists(ws.patch),
            skipped="none made",
        ),
        Step(
            "candidates",
            done(lambda: build_candidates.run(ws, extracts)),
            needed=lambda: candidates_stale(ws.candidates, stamps),
        ),
        Step("match", unless(lambda: match.run(ws, inputs.reg), Outcome.FAILED)),
        Step(
            "objects",
            done(lambda: locate.run(ws, inputs.reg, extracts)),
            needed=lambda: objects_stale(ws.objects, locate.wanted_refs(ws, inputs.reg), stamps),
        ),
        Step(
            "areas",
            done(lambda: build_dialect_areas.run(ws, inputs.reg, [area_extract])),
            needed=lambda: areas_stale(ws, area_stamps),
        ),
        Step(
            "dialect registry",
            done(lambda: registry.export_json(inputs.reg, ws.registry_json)),
        ),
        Step("search index", done(lambda: searchindex.run(ws, inputs.reg))),
        Step("curation worklist", done(lambda: curate.export(ws, inputs.reg))),
        Step("output check", unless(lambda: check_outputs.run(ws, inputs.reg), Outcome.FAILED)),
    ]


def outputs(ws: Workspace) -> list[str]:
    """The files of the repository a run may change."""
    return [
        ws.names,
        ws.curation,
        ws.report,
        ws.objects,
        ws.areas,
        ws.parts,
        ws.index,
        ws.registry_json,
    ]


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


def attempt(step: Step) -> Outcome:
    """Run a step; a problem that stops it is said and fails it."""
    try:
        return step.run()
    except PipelineError as stop:
        print(stop, file=sys.stderr)
        return Outcome.FAILED


def run(ws: Workspace, extracts: Sequence[str], area_extract: str | None = None) -> int:
    """Bring the workspace up to date from the OSM extracts its objects are
    in (see the module docstring); -> the exit status.  `area_extract`: the
    extract the dialect areas are built from, the first of `extracts` when
    None."""
    area_extract = area_extract or extracts[0]
    missing = [p for p in dict.fromkeys([*extracts, area_extract]) if not os.path.exists(p)]
    if missing:
        raise PipelineError(f"{', '.join(missing)} not found -- download it with `just extracts`")
    before = contents(outputs(ws))
    warned = []
    for step in steps(Inputs(ws, extracts, area_extract)):
        if not step.needed():
            print(f"== {step.name}: {step.skipped}")
            continue
        print(f"== {step.name}", flush=True)
        outcome = attempt(step)
        if outcome is Outcome.FAILED:
            print(f"update stopped: {step.name} failed")
            return 1
        if outcome is Outcome.WARNED:
            warned.append(step.name)
    print("== summary")
    print(summary(before, ws.worklist))
    if warned:
        print(f"update done, but look at the output of: {', '.join(warned)}")
        return 1
    return 0


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("update", __doc__)
    ap.add_argument(
        "extracts", nargs="+", metavar="PBF", help="the OSM extracts the name list's objects are in"
    )
    ap.add_argument(
        "--area-extract",
        metavar="PBF",
        help="the extract the dialect areas are built from (default: the first of the extracts)",
    )
    cli.add_workspace_options(ap, *cli.WORKSPACE_FILES, cli.WORK)
    a = ap.parse_args(argv)
    return run(cli.workspace(a), a.extracts, a.area_extract)
