"""The generated files of the pipeline, defined once: `OUTPUTS`.

Each `Output` says which files it is, what builds it and from what, and when
it is stale.  Everything that has to know the pipeline reads this table:

  frasch update         builds the outputs in the table's order -- one that
                        takes a scan of an extract only when it is stale
  frasch check-outputs  reports the committed ones that are stale, or that a
                        rebuild gives another file for
  frasch build <name>   builds one of them (`just rebuild <name>`)

A new generated file is a new entry here, and nothing else.

    frasch build <name> [<in.osm.pbf> ...] [--area-extract <pbf>]
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import enum
import filecmp
import io
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from frasch import (
    build_candidates,
    build_dialect_areas,
    cli,
    locate,
    match,
    osmscan,
    provenance,
    registry,
    searchindex,
)
from frasch.errors import PipelineError, rebuild
from frasch.objects import read_objects
from frasch.paths import Workspace
from frasch.provenance import ExtractStamp, Stamp
from frasch.registry import Registry


class From(enum.Enum):
    """What an output is built from, besides the hand-edited files."""

    FILES = "the other committed files alone"
    EXTRACTS = "the extracts the name list's objects are in"
    AREA_EXTRACT = "the extract the dialect areas are in"
    CANDIDATES = "the git-ignored candidates: it cannot be rebuilt in CI"


@dataclass(frozen=True)
class Extracts:
    """The OSM extracts a command was given."""

    objects: Sequence[str]  # those the name list's objects are in
    area: str  # the one the dialect areas are built from

    @classmethod
    def given(cls, pbfs: Sequence[str], area: str | None = None) -> Extracts | None:
        """The extracts a command was given, or None when it was given none.
        `area` is the first of `pbfs` when None.  Stops on a file that is
        not there."""
        named = list(dict.fromkeys([*pbfs, *([area] if area else [])]))
        if not named:
            return None
        missing = [pbf for pbf in named if not os.path.exists(pbf)]
        if missing:
            raise PipelineError(
                f"{', '.join(missing)} not found -- download it with `just extracts`"
            )
        return cls(list(pbfs) or named, area or named[0])


@dataclass(frozen=True)
class Run:
    """What a build or a check works on: a workspace, its dialect registry
    as read and checked, and the extracts -- None when none is at hand, as
    in CI."""

    ws: Workspace
    reg: Registry
    extracts: Extracts | None = None

    def pbfs(self, source: From) -> list[str] | None:
        """The extracts an output built from `source` reads; None when it
        reads none, or none is at hand."""
        if self.extracts is None:
            return None
        scanned = {
            From.EXTRACTS: list(self.extracts.objects),
            From.AREA_EXTRACT: [self.extracts.area],
        }
        return scanned.get(source)

    def stamps(self, source: From) -> list[ExtractStamp] | None:
        """`pbfs`, as a stamp records them."""
        pbfs = self.pbfs(source)
        return None if pbfs is None else osmscan.extract_stamps(pbfs)


@dataclass(frozen=True)
class Output:
    """One generated file of the pipeline (the dialect areas: two)."""

    name: str  # `frasch build <name>`
    what: str
    files: tuple[str, ...]  # by their attribute of the workspace
    source: From
    # writes the files in the run's workspace, from the extracts it reads
    make: Callable[[Run, Sequence[str]], None]
    # what a build would record now, given the stamps of the extracts it
    # reads (None: none, or not at hand); None for a file that carries no stamp
    stamp: Callable[[Run, Sequence[ExtractStamp] | None], Stamp] | None = None
    # a reason of its own why it is stale, besides the stamp
    outdated: Callable[[Run], str | None] | None = None
    committed: bool = True  # False for a git-ignored scratch file

    @property
    def recipe(self) -> str:
        """How to rebuild it, for a message."""
        return rebuild(self.name)

    @property
    def scans(self) -> bool:
        """Whether its build reads an extract -- the slow kind of build."""
        return self.source in (From.EXTRACTS, From.AREA_EXTRACT)

    def paths(self, ws: Workspace) -> list[str]:
        return [getattr(ws, name) for name in self.files]

    def build(self, run: Run) -> None:
        """Build it in the run's workspace; stops when it is built from
        extracts and the run has none."""
        pbfs = run.pbfs(self.source)
        if self.scans and pbfs is None:
            raise PipelineError(
                f"{self.name} is built from OSM extracts: name them, or run {self.recipe}"
            )
        self.make(run, pbfs or [])

    def due(self, run: Run) -> bool:
        """Whether `frasch update` builds it: every time -- unless its build
        scans an extract, then only when it is stale."""
        return not self.scans or self.stale(run) is not None

    def stale(self, run: Run) -> str | None:
        """Why the output has to be rebuilt, or None: a file of it is not
        there, or was built from other inputs than the run's -- the extracts
        among them only where the run has them at hand."""
        for path in self.paths(run.ws):
            if not os.path.exists(path):
                return f"{path} is not there"
        return self._behind(run) or (self.outdated(run) if self.outdated else None)

    def problems(self, run: Run, scratch: str) -> list[str]:
        """What `frasch check-outputs` finds wrong with it: it is stale, or
        a rebuild (into the directory `scratch`) gives another file.  One
        line, with the recipe that rebuilds it, or none."""
        try:
            reason = self.stale(run) or self._irreproducible(run, scratch)
        except PipelineError as stop:
            return [f"{self.paths(run.ws)[0]} cannot be rebuilt: {stop}"]
        return [f"{reason} -- rebuild it with {self.recipe}"] if reason else []

    def _irreproducible(self, run: Run, scratch: str) -> str | None:
        """Its first file that a rebuild from the run's inputs gives other
        bytes for -- when the run has what the build reads."""
        if self.source is From.CANDIDATES or (self.scans and run.extracts is None):
            return None
        rebuilt = {
            name: os.path.join(scratch, os.path.basename(path))
            for name, path in zip(self.files, self.paths(run.ws), strict=True)
        }
        with contextlib.redirect_stdout(io.StringIO()):  # a build says what it wrote
            self.build(dataclasses.replace(run, ws=dataclasses.replace(run.ws, **rebuilt)))
        for name, path in rebuilt.items():
            committed: str = getattr(run.ws, name)
            if not filecmp.cmp(committed, path, shallow=False):
                return f"{committed} is not what its inputs give"
        return None

    def _behind(self, run: Run) -> str | None:
        """Its first file whose stamp names other inputs than the run's."""
        if self.stamp is None:
            return None
        current = self.stamp(run, run.stamps(self.source))
        for path in self.paths(run.ws):
            differing = (Stamp.read(path) or _NO_STAMP).other_than(current)
            if differing:
                return f"{path} was not built from the current {_listed(differing)}"
        return None


def _listed(names: Sequence[str]) -> str:
    """`a, b and c`."""
    return " and ".join([", ".join(names[:-1]), names[-1]] if names[1:] else names)


# what a file without a stamp was built from: nothing that is there now
_NO_STAMP = Stamp({}, [])


def _other_references(run: Run) -> str | None:
    """The objects file, when it was located for other references than the
    rows on the map name now.  One that no extract holds was asked for, and
    is no reason to locate again: only its row can help it."""
    wanted = locate.wanted_refs(run.ws, run.reg)
    asked = read_objects(run.ws.objects).asked
    changes = {"new": len(wanted - asked), "no longer named": len(asked - wanted)}
    if not any(changes.values()):
        return None
    counts = ", ".join(f"{count} {what}" for what, count in changes.items() if count)
    return (
        f"{run.ws.objects} was located for other references than the rows on the map "
        f"name now ({counts})"
    )


def _report_stamp(run: Run, _extracts: object) -> Stamp:
    """What the matcher would stamp its report with now.  Its extracts are
    those of the candidates, not the run's: the report is stale once the
    candidates were scanned again, which is when a rebuild helps.  Like any
    extracts, they count only in a run that has extracts at hand -- the
    candidates are scratch files, and must not decide what CI's check says."""
    candidates = Stamp.read(run.ws.candidates) if run.extracts else None
    return match.stamp(run.ws, candidates.extracts if candidates else None)


def _match(run: Run, _extracts: Sequence[str]) -> None:
    """Run the matcher, which says itself what it could not do."""
    if match.run(run.ws, run.reg):
        raise PipelineError("the matcher could not finish")


OUTPUTS = (
    Output(
        "candidates",
        "every object of the extracts that could be a place",
        files=("candidates",),
        source=From.EXTRACTS,
        make=lambda run, pbfs: build_candidates.run(run.ws, pbfs),
        stamp=lambda run, extracts: Stamp.of({}, extracts),
        committed=False,
    ),
    Output(
        "report",
        "the matcher's hand-review worklist (the matcher fills the name list's osm cells too)",
        files=("report",),
        source=From.CANDIDATES,
        make=_match,
        stamp=_report_stamp,
    ),
    Output(
        "objects",
        "where the name list's objects are",
        files=("objects",),
        source=From.EXTRACTS,
        make=lambda run, pbfs: locate.run(run.ws, run.reg, pbfs),
        stamp=lambda run, extracts: Stamp.of({}, extracts),
        outdated=_other_references,
    ),
    Output(
        "areas",
        "the dialect areas, and their parts for the review overlay",
        files=("areas", "parts"),
        source=From.AREA_EXTRACT,
        make=lambda run, pbfs: build_dialect_areas.run(run.ws, run.reg, pbfs),
        stamp=lambda run, extracts: build_dialect_areas.stamp(run.ws, extracts),
    ),
    Output(
        "dialects",
        "the dialect registry as the frontend compiles it in",
        files=("registry_json",),
        source=From.FILES,
        make=lambda run, _: registry.export_json(run.reg, run.ws.registry_json),
    ),
    Output(
        "index",
        "the search index of the site",
        files=("index",),
        source=From.FILES,
        make=lambda run, _: searchindex.run(run.ws, run.reg),
        # its extracts are those of the objects file
        stamp=lambda run, _: provenance.stamp(run.ws),
    ),
)


def add_area_extract_option(ap: argparse.ArgumentParser) -> None:
    """`--area-extract`, for a command that takes extracts."""
    ap.add_argument(
        "--area-extract",
        metavar="PBF",
        help="the extract the dialect areas are built from (default: the first of the extracts)",
    )


def output(name: str) -> Output:
    """The output with this name."""
    return next(found for found in OUTPUTS if found.name == name)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("build", __doc__)
    ap.epilog = "outputs:\n" + "\n".join(f"  {found.name:<11} {found.what}" for found in OUTPUTS)
    ap.add_argument(
        "output",
        choices=[found.name for found in OUTPUTS],
        metavar="output",
        help="the generated file to build, by its name (listed below)",
    )
    ap.add_argument(
        "extracts",
        nargs="*",
        metavar="PBF",
        help="the OSM extracts the name list's objects are in; only an output built from "
        "them reads them",
    )
    add_area_extract_option(ap)
    ap.add_argument(
        "--scans",
        action="store_true",
        help="build nothing: only say by the exit status whether the output is built from "
        "the extracts (0) or not (1) -- `just rebuild` asks, and downloads them only then",
    )
    cli.add_workspace_options(ap, *cli.WORKSPACE_FILES, cli.WORK)
    a = ap.parse_args(argv)
    found = output(a.output)
    if a.scans:
        return 0 if found.scans else 1
    ws = cli.workspace(a)
    # an output that scans no extract is built whether or not they are there
    extracts = Extracts.given(a.extracts, a.area_extract) if found.scans else None
    found.build(Run(ws, registry.read(ws.dialects), extracts))
    return 0
