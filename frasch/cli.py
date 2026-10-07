"""What every command shares.  Its argument parser (`parser`).  Its path
options: a command lists the files of the workspace it works on
(`add_workspace_options`), and each gets the same option, default and help
in every command.  And its `main`, which stops on a PipelineError with the
message and exit status 1 -- the library below raises, only here does a
problem become an exit code."""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import sys
from collections.abc import Sequence
from typing import Protocol

from frasch import paths
from frasch.errors import PipelineError
from frasch.paths import Workspace

# the files a command can take a path for, by their attribute of the
# workspace: what the option's help calls them
WORKSPACE_FILES = {
    "names": "the name list",
    "dialects": "the dialect registry",
    "curation": "the map curation",
    "area_list": "the dialect area list",
    "areas": "the dialect areas, one feature per dialect",
    "parts": "the dialect areas by municipality, for the review overlay",
    "objects": "where the name list's objects are",
    "report": "the hand-review worklist of the matcher",
    "index": "the search index",
    "registry_json": "the dialect registry as the frontend compiles it in",
    "candidates": "every object of the extracts that could be a place",
    "matches": "the details of the last match",
    "wikidata_cache": "the country lookups already made",
    "worklist": "the rows left for the curation view",
    "patch": "the decisions made in the curation view",
}
# not a file: the directory of the scratch files, the lock among them
WORK = "work"


def parser(command: str, description: str | None) -> argparse.ArgumentParser:
    """The argument parser of `frasch <command>`.  It takes an option by its
    full name only: an abbreviation would pass for another option, as the
    `--registry` that once named dialects.csv would for `--registry-json`."""
    return argparse.ArgumentParser(
        prog=f"frasch {command}",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )


def add_workspace_options(ap: argparse.ArgumentParser, *names: str) -> None:
    """Give a command the path options of the files it works on: `--<file>`
    for each attribute of the workspace in `names`, and `--work` for "work"."""
    default = Workspace.default()
    for name in names:
        if name == WORK:
            what, path = "the directory of the scratch files", os.path.dirname(default.lock)
        else:
            what, path = WORKSPACE_FILES[name], getattr(default, name)
        ap.add_argument(
            "--" + name.replace("_", "-"),
            metavar="PATH",
            help=f"{what} (default: {os.path.relpath(path, paths.ROOT)})",
        )


def workspace(args: argparse.Namespace) -> Workspace:
    """The workspace a command was asked to work on: the default one, with
    the files its path options name."""
    found = Workspace.default()
    if work := getattr(args, WORK, None):
        found = found.with_work(work)
    named = {name: getattr(args, name, None) for name in WORKSPACE_FILES}
    return dataclasses.replace(found, **{k: v for k, v in named.items() if v is not None})


class Command(Protocol):
    """A command's `main`: the arguments (None = the process's own) -> the
    exit status."""

    def __call__(self, argv: Sequence[str] | None = None) -> int: ...


def command(main: Command) -> Command:
    """Decorate a command's `main(argv=None) -> int`."""

    @functools.wraps(main)
    def run(argv: Sequence[str] | None = None) -> int:
        try:
            return main(argv)
        except PipelineError as exc:
            print(exc, file=sys.stderr)
            return 1

    return run
