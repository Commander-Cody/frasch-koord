"""What every command shares: its `main` stops on a PipelineError with the
message and exit status 1 -- the library below raises, only here does a
problem become an exit code."""
from __future__ import annotations

import functools
import sys
from collections.abc import Sequence
from typing import Protocol

from frasch.errors import PipelineError


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
