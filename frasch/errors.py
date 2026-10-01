"""What the pipeline raises when it cannot go on.  Library code only raises;
a command's `main` (see frasch.cli) turns these into their message and exit
status 1, anything else stays a crash with a traceback."""

from __future__ import annotations


class PipelineError(Exception):
    """A problem the user has to fix -- a broken input, a missing file, a
    file someone else is writing -- as opposed to a bug."""


class ValidationError(PipelineError, ValueError):
    """An input breaks the rules of its file.  Carries every problem found,
    one `where: reason` string each, where the reader collects them all."""

    def __init__(self, problems: list[str] | str):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("\n".join(self.problems))


class Invalid(ValidationError):
    """One cell that breaks the rules.  `reason` is the bare reason, for
    names/check.py, which says where itself."""

    def __init__(self, where: str, reason: str):
        super().__init__(f"{where}: {reason}" if where else reason)
        self.reason = reason


class Conflict(PipelineError):
    """The file changed on disk between reading and writing it."""
