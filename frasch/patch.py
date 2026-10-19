"""names/work/curate-patch.jsonl -- the decisions of the curation view (web/,
`?curate`), as `frasch curate apply` reads them.

The browser decides one row at a time and the Vite dev server appends each
decision as a line, never rewriting one: a row decided twice has two lines
and the last counts, `clear` withdraws.  names/curate-patch.schema.json is
the contract of a line -- what every entry has, and per action the fields it
needs and may carry; the dev server and apply both check a line against it.

Apply takes the file out of the browser's way before it reads it
(`take_snapshot`), so that a decision made meanwhile starts a fresh patch;
what it refused goes back (`append_back`), and a failed apply puts the whole
file back (`restore_patch`).
"""

from __future__ import annotations

import dataclasses
import functools
import io
import json
import os
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any, NotRequired, TypedDict, final

import jsonschema

from frasch import paths
from frasch.paths import StrPath


class PatchEntry(TypedDict):
    """One line of the patch, as names/curate-patch.schema.json allows it."""

    id: str
    action: str  # one of the schema's enum: an entry of `decisions.ACTIONS`
    line: NotRequired[int]
    kind: NotRequired[str]
    name: NotRequired[str]
    de: NotRequired[str]
    osm: NotRequired[str]
    wikidata: NotRequired[str]
    slug: NotRequired[str]
    lat: NotRequired[float]
    lon: NotRequired[float]
    polygon_km2: NotRequired[float]
    names: NotRequired[dict[str, str]]
    note: NotRequired[str]
    at: NotRequired[str]


@final
@dataclasses.dataclass(frozen=True)
class EntryLine:
    """A valid line of the patch as apply read it."""

    number: int  # its line in the patch
    entry: PatchEntry

    @property
    def value(self) -> object:
        """The line's JSON value, as the patch holds it."""
        return self.entry


@final
@dataclasses.dataclass(frozen=True)
class RefusedLine:
    """A line of the patch that is no valid entry, as apply read it."""

    number: int  # its line in the patch
    value: object  # the line's JSON value, as the patch holds it
    problem: str  # what makes it no valid entry


PatchLine = EntryLine | RefusedLine


# The actions about a place the view created (#113), rather than about its
# location: such a place has two slots under its key, the place itself and
# its decision, and each has its own last entry.
PLACE_ACTIONS = frozenset({"create", "discard"})

# The slot of an entry under its key: the place itself, or its decision.
PLACE, DECISION = "place", "decision"

# What makes two patch entries say the same thing: the key, and the slot.
PatchKey = tuple[str, str]


def patch_key(value: object) -> PatchKey | None:
    """What makes two patch entries decisions about the same thing: the id of
    their row (or the provisional key of a created place), and whether they
    are about the place itself or its decision.  The `line`, `name` and `de`
    an entry also carries are only there for the messages -- they change when
    the list is edited, the id does not.  None for a line (as the patch
    holds it) without a usable id."""
    if not isinstance(value, dict):
        return None
    ident = value.get("id")
    if not isinstance(ident, str) or not ident:
        return None
    return ident, PLACE if value.get("action") in PLACE_ACTIONS else DECISION


def withdrawn(newest: Iterable[object]) -> set[PatchKey]:
    """The keys the newest entries (the lines' values, as the patch holds
    them) withdraw besides their own: a `discard` withdraws the decision of
    its place as well."""
    return {
        (key[0], DECISION)
        for value in newest
        if isinstance(value, dict)
        and value.get("action") == "discard"
        and (key := patch_key(value))
    }


def read_patch(
    path: StrPath, not_json: Callable[[int, ValueError], object] = lambda n, exc: None
) -> list[PatchLine]:
    """-> the last entry per row, in line order.  The browser appends, never
    rewrites, so a row decided twice simply has two lines; `clear` withdraws,
    whatever line either was sent with.  A place the view created has two
    lines of its own under its key, the place (`create`) and its decision;
    `discard` withdraws both.

    A line that breaks the patch schema counts like any other: apply
    refuses and keeps it, and as the newest line about its row it holds
    back the row's earlier decision.  A line without a usable id is a
    decision of its own, never swallowed by a later one.  A line that is no
    JSON is left out and goes to `not_json` with its number."""
    last: dict[PatchKey | tuple[str, int], PatchLine] = {}
    with open(path, encoding="utf-8") as fh:
        for line in patch_lines(fh, not_json):
            last[patch_key(line.value) or ("line", line.number)] = line
    gone = withdrawn(line.value for line in last.values())
    return sorted((line for key, line in last.items() if key not in gone), key=_patch_order)


def patch_lines(
    text: Iterable[str], not_json: Callable[[int, ValueError], object] = lambda n, exc: None
) -> Iterator[PatchLine]:
    """The lines of a patch (its text, a newline-ended line at a time, as
    a file gives it) as apply reads them, blank ones left out; a line that
    is no JSON goes to `not_json` with its number instead."""
    for n, line in enumerate(text, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError as exc:
            not_json(n, exc)
            continue
        yield patch_line(value, n)


def patch_line(value: Any, n: int) -> PatchLine:
    """One parsed line of the patch as apply handles it: the entry plus its
    line, or the line's value and what makes it no valid entry."""
    why = (
        schema_problem(value)
        if isinstance(value, dict)
        else "not a JSON object (curate-patch.schema.json)"
    )
    if why:
        return RefusedLine(n, value, why)
    entry: PatchEntry = value  # valid: the schema's shape
    return EntryLine(n, entry)


def _patch_order(line: PatchLine) -> tuple[int, int]:
    """Places.csv order (the row's `line` when the worklist was exported),
    then patch order."""
    row_line = line.entry.get("line") if isinstance(line, EntryLine) else None
    return (row_line or 0, line.number)


def names_of(line: PatchLine) -> str:
    """`name / de` of the row a line is about, for the messages."""
    fields = line.value if isinstance(line.value, dict) else {}
    return f"{fields.get('name')} / {fields.get('de')}"


@functools.cache
def patch_validator() -> jsonschema.Draft202012Validator:
    with open(paths.PATCH_SCHEMA, encoding="utf-8") as fh:
        return jsonschema.Draft202012Validator(json.load(fh))


def schema_problem(entry: object) -> str | None:
    """What breaks names/curate-patch.schema.json in one entry, or None."""
    error = min(patch_validator().iter_errors(entry), key=_telling_first, default=None)
    if error is None:
        return None
    where = "/".join(map(str, error.absolute_path))
    return f"{where + ': ' if where else ''}{error.message} (curate-patch.schema.json)"


def _telling_first(error: jsonschema.ValidationError) -> tuple[bool, str]:
    """Orders the errors of an entry: a field no branch of the schema
    evaluated comes last.  That is the problem of an entry with a field of
    another action -- but an action's branch that fails for another reason
    evaluates none of its fields, and the schema then calls them all
    unexpected too."""
    return error.validator == "unevaluatedProperties", str(error)


def take_snapshot(patch: str) -> str:
    """Rename the patch to `<stamp>.applied.jsonl`; -> the new name."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root, ext = os.path.splitext(patch)
    snapshot = f"{root}.{stamp}.applied{ext}"
    os.rename(patch, snapshot)
    return snapshot


def append_back(path: str, refused: Iterable[PatchLine]) -> int:
    """Append refused lines to the live patch -- appending, never
    rewriting, because the dev server may be appending to it too.  A line
    whose row has been decided again since then is dropped: the newer
    decision wins, as it would in `read_patch` -- and a discarded place takes
    its decision along.  -> how many were appended."""
    newer: set[PatchKey] = set()
    ends_nl = True
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        ends_nl = not text or text.endswith("\n")
        # line by line as a file is read (not `splitlines`, which also ends
        # a line inside a JSON string that holds a U+2028)
        values = [line.value for line in patch_lines(io.StringIO(text))]
        newer = {key for key in map(patch_key, values) if key} | withdrawn(values)
    lines = [
        json.dumps(line.value, ensure_ascii=False) + "\n"
        for line in refused
        if patch_key(line.value) not in newer
    ]
    if lines:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(("" if ends_nl else "\n") + "".join(lines))
    return len(lines)


def restore_patch(snapshot: str, path: str) -> None:
    """Undo taking the snapshot after a failed apply: the snapshot becomes the
    patch again, followed by whatever the browser appended in the meantime."""
    while True:
        try:
            os.link(snapshot, path)  # unlike rename, never overwrites
            os.unlink(snapshot)
            return
        except FileExistsError:
            pass
        # the browser started a new patch: move it aside (the next pick starts
        # yet another, hence the loop) and put its entries after the old ones
        newer = f"{snapshot}.newer"
        os.rename(path, newer)
        with open(newer, "rb") as fh:
            text = fh.read()
        with open(snapshot, "rb") as fh:
            old = fh.read()
        with open(snapshot, "ab") as fh:
            fh.write((b"" if not old or old.endswith(b"\n") else b"\n") + text)
        os.unlink(newer)
