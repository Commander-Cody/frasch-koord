"""What every command shares: its `main` stops on a PipelineError with the
message and exit status 1 -- the library below raises, only here does a
problem become an exit code."""
from __future__ import annotations

import functools
import sys

from frasch.errors import PipelineError


def command(main):
    """Decorate a command's `main(argv=None) -> int`."""
    @functools.wraps(main)
    def run(argv=None):
        try:
            return main(argv)
        except PipelineError as exc:
            print(exc, file=sys.stderr)
            return 1
    return run
