"""What the pipeline raises when it cannot go on.  Library code only raises;
a command's `main` (see frasch.cli) turns these into their message and exit
status 1, anything else stays a crash with a traceback."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class PipelineError(Exception):
    """A problem the user has to fix -- a broken input, a missing file, a
    file someone else is writing -- as opposed to a bug."""


def text(error: BaseException) -> str:
    """What an error says: its message, and under it its notes -- what
    became of the files, as the code it passed through on its way up added
    it (`add_note`)."""
    return "\n".join([str(error), *getattr(error, "__notes__", ())])


def rebuild(output: str) -> str:
    """How to rebuild a generated file, for a message that says so: the
    recipe of the output with this name in the pipeline's table
    (frasch.pipeline)."""
    return f"`just rebuild {output}`"


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a hand-edited file, and the line it is on (the
    header is line 1)."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


class ValidationError(PipelineError, ValueError):
    """A hand-edited file breaks its rules.  Carries every problem found,
    where the reader collects them all."""

    def __init__(self, problems: Sequence[Problem]):
        self.problems = list(problems)
        super().__init__("\n".join(str(p) for p in self.problems))


class Invalid(PipelineError, ValueError):
    """One cell that breaks the rules.  `reason` is the bare reason, for the
    reader of the cell's file, which says where itself."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Conflict(PipelineError):
    """The file changed on disk between reading and writing it."""
