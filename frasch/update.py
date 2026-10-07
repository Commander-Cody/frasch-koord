"""Bring every file the name list feeds up to date, in one run (`just update`).

    frasch update <in.osm.pbf> [<in.osm.pbf> ...] [--area-extract <pbf>]

After an edit to places.csv, or a session in the curation view (`?curate`),
this runs, in order:

  ids and input check `check-inputs --fix`: give new rows an `id`, check the
                      hand-edited files
  curation decisions  `curate apply`, when the view left a patch
  the outputs         every generated file of the pipeline's table
                      (frasch.pipeline), in its order: the candidates, the
                      matcher with its report, the objects, the dialect
                      areas, the dialect registry, the search index
  curation worklist   `curate export`: what is left for the view
  output check        `check-outputs`: the committed outputs match their inputs

and ends with the files it changed and the rows left to curate.  An output
whose build scans an extract -- the candidates, the objects, the dialect
areas -- is skipped while it is not stale (`Output.due`); the others are
built every time.  A step that fails stops the run.  A decision `apply` refuses does not: it stays in the patch,
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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from frasch import check_inputs, check_outputs, cli, curate, files, pipeline
from frasch.errors import PipelineError
from frasch.paths import Workspace
from frasch.pipeline import Extracts, Output, Run
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


@dataclass
class Inputs:
    """What a run works on: its workspace and extracts, and the dialect
    registry once the first step has read and checked it -- the file is read
    that once, and every later step works on the same registry."""

    ws: Workspace
    extracts: Extracts
    checked: Registry | None = None

    @property
    def reg(self) -> Registry:
        if self.checked is None:
            raise RuntimeError("the dialect registry is asked for before the input check has run")
        return self.checked

    @property
    def run(self) -> Run:
        """What the outputs are built from."""
        return Run(self.ws, self.reg, self.extracts)

    def check(self) -> Outcome:
        """The first step: give new rows an id and check the hand-edited files."""
        found = check_inputs.run(self.ws, fix=True)
        self.checked = found.registry
        return Outcome.FAILED if found.problems else Outcome.DONE


def steps(inputs: Inputs) -> list[Step]:
    """The run's steps, in order: around the outputs of the pipeline's table,
    what is no output -- the inputs' check, the curation and the last check."""
    ws = inputs.ws
    return [
        Step("ids and input check", inputs.check),
        Step(
            "curation decisions",
            unless(lambda: curate.apply(ws, inputs.reg), Outcome.WARNED),
            needed=lambda: os.path.exists(ws.patch),
            skipped="none made",
        ),
        *(build_step(output, inputs) for output in pipeline.OUTPUTS),
        Step("curation worklist", done(lambda: curate.export(ws, inputs.reg))),
        # without the extracts: with them, the check would scan them again
        Step(
            "output check",
            unless(lambda: check_outputs.run(Run(ws, inputs.reg)), Outcome.FAILED),
        ),
    ]


def build_step(output: Output, inputs: Inputs) -> Step:
    """The step that builds an output, when it is due."""
    return Step(
        output.name,
        done(lambda: output.build(inputs.run)),
        needed=lambda: output.due(inputs.run),
    )


def tracked(ws: Workspace) -> list[str]:
    """The files of the repository a run may change: the two it edits, and
    the committed outputs."""
    built = [path for output in pipeline.OUTPUTS if output.committed for path in output.paths(ws)]
    return [ws.names, ws.curation, *built]


def contents(paths: Sequence[str]) -> dict[str, str]:
    """Each file's fingerprint."""
    return {path: files.fingerprint(path) for path in paths}


def summary(before: Mapping[str, str], worklist: str) -> str:
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
    given = Extracts.given(extracts, area_extract)
    if given is None:
        raise PipelineError("no OSM extract to bring the name files up to date from")
    before = contents(tracked(ws))
    warned = []
    for step in steps(Inputs(ws, given)):
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
    pipeline.add_area_extract_option(ap)
    cli.add_workspace_options(ap, *cli.WORKSPACE_FILES, cli.WORK)
    a = ap.parse_args(argv)
    return run(cli.workspace(a), a.extracts, a.area_extract)
