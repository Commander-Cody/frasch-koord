"""`frasch <command>`: the one entry point of the pipeline.

Each command is a module with a `main(argv)`; this is the table of them, by
the names the just recipes use.  `frasch <command> --help` explains a
command and its options.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence

from frasch.cli import Command

# command -> (its module, what it does), in the pipeline's order
COMMANDS = {
    "check-inputs": ("check_inputs", "check the hand-edited name files for damage"),
    "candidates": ("build_candidates", "scan OSM extracts for every object that could be a place"),
    "match": ("match", "fill the empty osm cells of the name list"),
    "areas": ("build_dialect_areas", "build the dialect areas from the area list"),
    "dialects": ("registry", "print the dialect registry"),
    "build": ("pipeline", "build one of the pipeline's generated files"),
    "provenance": ("provenance", "print what the index and the tiles are built from"),
    "update": ("update", "bring every file the name list feeds up to date"),
    "check-outputs": ("check_outputs", "prove the committed outputs match their inputs"),
    "curate": ("curate", "export the curation worklist, or apply the view's decisions"),
    "inject": ("inject_names", "copy an OSM extract with the names added as tags"),
    "check-tiles": ("check_tiles", "compare a built tile archive with the search index"),
}


def command(name: str) -> Command:
    """The `main` of a command.  Its module is imported only now: a command
    does not pay for the libraries of the others."""
    module, _ = COMMANDS[name]
    main: Command = importlib.import_module(f"frasch.{module}").main
    return main


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = argparse.ArgumentParser(
        prog="frasch",
        description=__doc__.split("\n\n")[0],
        epilog="commands:\n"
        + "\n".join(f"  {name:<14} {what}" for name, (_, what) in COMMANDS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    ap.add_argument("command", choices=list(COMMANDS), metavar="command")
    # only the command's name is parsed here: what follows it is the command's own
    name: str = ap.parse_args(argv[:1]).command
    return command(name)(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
