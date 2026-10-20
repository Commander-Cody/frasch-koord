"""Put the review worklist of `frasch match` on the map, and write the answers
back into the name list.

The matcher leaves two kinds of row for a human: `ambiguous` (several plausible
OSM objects) and `not_found` (no object, or only near misses).  Deciding them
from REPORT.md means looking every candidate up on openstreetmap.org; on a map
the answer is usually obvious at a glance.  So:

    frasch curate export  ->  names/work/curate.json   (the worklist, see
                          frasch.worklist)
       the browser (web/, `?curate`, Vite dev server only) shows them as pins
       and appends one decision per line to names/work/curate-patch.jsonl
       (frasch.patch)
    frasch curate apply   <-  names/work/curate-patch.jsonl

This module is the command, and `apply`: the transaction that writes the
decisions (frasch.decisions says what each makes of its row).

What apply writes where
  names/places.csv         only `osm`, `wikidata` and `status` of the
                           rows the matcher owns -- the same cells it
                           writes itself, and never a row a human has already decided
                           (status ok/skip, a hand-filled reference, a local
                           reference, `not_a_place`) or one without a Frisian
                           name, and never an object or
                           Wikidata item another row holds: the name list
                           would be refused.  And the new rows of the places
                           the view created (frasch.newplaces), each with its
                           decision -- which it takes also without a Frisian
                           name -- or not at all.  Review with `git diff`.
  names/curation.csv       one appended row per `local` decision (a
                           place OSM does not have -- it needs a position).
  names/work/curate-patch.jsonl
                           renamed to `<stamp>.applied.jsonl` before
                           it is read, so that a decision the browser makes
                           meanwhile starts a fresh patch (`--keep` leaves it
                           alone); an entry apply refused is appended back so
                           it is not lost.  If apply fails, the patch is put
                           back.

Apply checks everything first and then writes curation.csv and places.csv, each
in one step and only if it did not change on disk meanwhile; when the second
write fails, the first is undone, so a failed apply changes neither file.
names/work/.lock keeps it from running at the same time as `frasch match` or
`frasch check-inputs --fix`.

Neither `apply` nor the export prints: each returns a report, and the command
(as `frasch update`, which runs both) prints it.

Run:  frasch curate                    # = export
      frasch curate apply --dry-run
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import final

from frasch import (
    cli,
    curationlist,
    dialects,
    errors,
    files,
    newplaces,
    patch,
    placelist,
    worklist,
)
from frasch.curationlist import Appendable
from frasch.decisions import ACTIONS, Decision, Refused, Standing, owner_problem
from frasch.dialects import Registry
from frasch.errors import PipelineError
from frasch.patch import EntryLine, PatchLine, RefusedLine
from frasch.paths import Workspace
from frasch.placelist import PlaceList, PlaceRow


@final
@dataclasses.dataclass(frozen=True)
class Refusal:
    """A line of the patch apply refused, and why."""

    line: PatchLine
    why: str


@dataclasses.dataclass
class ApplyReport:
    """What an apply made of the patch, for the command to print.  An apply
    that fails raises instead: the warnings and the log are then the notes of
    its error."""

    applied: int = 0  # the rows it decided -- on a dry run, would decide
    created: int = 0  # the rows it inserted -- on a dry run, would insert
    # the lines it refused: they stay in the patch
    refused: list[Refusal] = dataclasses.field(default_factory=list)
    # what it did, a line each: every decision, then where the patch went
    log: list[str] = dataclasses.field(default_factory=list)
    # the lines of the patch it could not read
    warnings: list[str] = dataclasses.field(default_factory=list)

    def refuse(self, line: PatchLine, why: str) -> None:
        self.refused.append(Refusal(line, why))
        self.log.append(f"  refused patch line {line.number} ({patch.names_of(line)}): {why}")


def apply(
    ws: Workspace, reg: Registry, *, dry_run: bool = False, keep: bool = False
) -> ApplyReport:
    """Write the decisions of the workspace's patch into its name list and
    curation (see the module docstring); -> what it did.  The decisions it
    refused stay in the patch; a problem that stops the whole apply raises,
    and its report goes with the error as notes: what it had to say until
    then, and what became of the files.  `dry_run`: say what would change and
    write nothing.  `keep`: leave the patch file where it is."""
    with files.lock(ws.lock):
        return _apply(ws, reg, dry_run, keep)


def _apply(ws: Workspace, reg: Registry, dry_run: bool, keep: bool) -> ApplyReport:
    # Everything that can refuse the whole run is checked before the patch is
    # touched: the name list, and curation.csv (read once, kept as bytes, so
    # the rows appended to it land after exactly what was checked).
    lists = _Lists(placelist.read(ws.names, reg), curationlist.read_for_appending(ws.curation))
    if not os.path.exists(ws.patch):
        raise PipelineError(
            f"{ws.patch} not found -- decide some rows in the browser first (web/, `?curate`)"
        )
    # Take the patch out of the browser's way first, then read it: the dev
    # server appends with O_APPEND, so a decision made from now on starts
    # a fresh patch file instead of landing in one that is being archived.
    snapshot = None if dry_run or keep else patch.take_snapshot(ws.patch)
    decisions = _Decisions()
    report = decisions.report
    try:
        _enter_patch(snapshot or ws.patch, lists, decisions)
        if not dry_run:
            _write(lists, decisions)
    except BaseException as failed:
        if snapshot:
            patch.restore_patch(snapshot, ws.patch)
            report.log.append(f"nothing applied -- {ws.patch} restored")
        # the report is lost with the error: what it says goes with that
        for line in (*report.warnings, *report.log):
            failed.add_note(line)
        raise
    if snapshot:
        report.log += _keep_refused(snapshot, ws.patch, [r.line for r in report.refused])
    report.log.append(_sum(decisions, lists, dry_run))
    return report


def _sum(decisions: _Decisions, lists: _Lists, dry_run: bool) -> str:
    """The last line of the log: how many rows changed, were appended and refused."""
    report = decisions.report
    applied, created, refused = report.applied, report.created, len(report.refused)
    appended = len(decisions.new_curation)
    if dry_run:
        return (
            f"dry run: {applied} row(s) would change, {created} would be created, "
            f"{appended} curation row(s) would be appended, "
            f"{refused} refused -- nothing written"
        )
    return (
        f"{applied} row(s) written to {lists.places.path}, {created} created, "
        f"{appended} appended to {lists.curation.path}, {refused} refused"
    )


@dataclasses.dataclass
class _Lists:
    """The name list and curation.csv, as apply checked them."""

    places: PlaceList
    curation: Appendable

    @functools.cached_property
    def by_id(self) -> dict[str, PlaceRow]:
        return {r["id"]: r for r in self.places.rows}

    def row_to_fill(self, ident: str) -> PlaceRow:
        """The row with this id, which a decision may fill."""
        row = self.by_id.get(ident)
        if row is None and newplaces.is_provisional(ident):
            raise Refused(
                f"no place {ident} is created in the patch (applied or discarded already?)"
            )
        if row is None:
            raise Refused(
                f"no row with id {ident!r} in {self.places.path} (deleted since the export?)"
            )
        if why := owner_problem(row, self.places):
            raise Refused(why)
        return row

    def standing_for(self, row: PlaceRow) -> Standing:
        """How the lists stand for a decision about `row`, with the
        decisions applied so far: what the other rows hold (claim -> the
        line of its row), and every local reference there is."""
        others = [other for other in self.places.rows if other is not row]
        claimed = {key: other.line for other in others for key in placelist.claims(other).keys}
        slugs = self.curation.slugs | {r.local for r in self.places.rows if r.local}
        return Standing(self.places.reg, self.curation.path, claimed, slugs)


@dataclasses.dataclass
class _Decisions:
    """What apply made of the patch's entries."""

    report: ApplyReport = dataclasses.field(default_factory=ApplyReport)
    new_curation: list[dict[str, str]] = dataclasses.field(default_factory=list)
    # the rows of the created places, with their decisions: logged once all
    # are in the list, since a place inserted above a row moves it down
    created: list[tuple[PlaceRow, Decision | None]] = dataclasses.field(default_factory=list)

    def create(self, row: PlaceRow, decision: Decision | None, names: PlaceList) -> None:
        """Insert a created place's row into the list, with its decision --
        the file is written at the end, the log by `say_created`."""
        newplaces.insert(row, names)
        self.report.created += 1
        if decision:
            self._write(row, decision)
        self.created.append((row, decision))

    def say_created(self, names: PlaceList) -> None:
        """Log the created places and their decisions, at their lines."""
        for row, decision in self.created:
            self.report.log.append(
                f"  {names.path}:{row.line} {placelist.describe(row, names.reg)}: "
                f"new {row['kind']} row, id = {row['id']}"
            )
            if decision:
                self.report.log.append(_said(row, decision, names))

    def take(self, row: PlaceRow, decision: Decision, names: PlaceList) -> None:
        """Write a decision into its row -- the file is written at the end."""
        self._write(row, decision)
        self.report.log.append(_said(row, decision, names))

    def _write(self, row: PlaceRow, decision: Decision) -> None:
        decision.reference.write(row)
        if decision.curation:
            self.new_curation.append(decision.curation)
        self.report.applied += 1


def _said(row: PlaceRow, decision: Decision, names: PlaceList) -> str:
    """The log line of a decision."""
    return f"  {names.path}:{row.line} {placelist.describe(row, names.reg)}: {decision.text}"


def _enter_patch(patch_file: str, lists: _Lists, decisions: _Decisions) -> None:
    """Enter every entry of the patch file into its row of the lists (in
    memory), or refuse it."""

    def not_json(n: int, exc: ValueError) -> None:
        decisions.report.warnings.append(f"{patch_file}:{n}: not JSON ({exc}) -- ignored")

    lines = patch.read_patch(patch_file, not_json)
    places = {key: line for line in lines if (key := _place_key(line))}
    decided = {key: line for line in lines if (key := _decision_key(line)) in places}
    for key, place in places.items():
        _enter_place(place, decided.get(key), lists, decisions)
    decisions.say_created(lists.places)
    for line in lines:
        if not _place_key(line) and _decision_key(line) not in places:
            _enter_line(line, lists, decisions)


def _place_key(line: PatchLine) -> str | None:
    """The provisional key of the created place a line is about itself
    (`create`, `discard`), or None -- also for such a line under a row's id,
    which the schema refuses on its own."""
    key = patch.patch_key(line.value)
    if key and key[1] == patch.PLACE and newplaces.is_provisional(key[0]):
        return key[0]
    return None


def _decision_key(line: PatchLine) -> str | None:
    """The row id or provisional key a line decides, or None."""
    key = patch.patch_key(line.value)
    return key[0] if key and key[1] == patch.DECISION else None


def _enter_line(line: PatchLine, lists: _Lists, decisions: _Decisions) -> None:
    """Enter one line of the patch into its row, or refuse it."""
    try:
        decided = _decided(line, lists.row_to_fill, lists)
    except Refused as why:
        decisions.report.refuse(line, str(why))
        return
    if decided:
        decisions.take(*decided, lists.places)


def _enter_place(
    place: PatchLine, decision: PatchLine | None, lists: _Lists, decisions: _Decisions
) -> None:
    """Enter a place the view created into the list, with its decision -- or
    refuse both: neither is applied without the other."""
    if isinstance(place, EntryLine) and place.entry["action"] == "discard":
        return  # discarded in the browser, its decision with it
    report = decisions.report
    try:
        row = _created_row(place, lists)
    except Refused as why:
        report.refuse(place, str(why))
        if decision:
            report.refuse(decision, f"its place {_place_key(place)} is refused")
        return
    decided = None
    if decision:
        try:
            decided = _decided(decision, lambda _: row, lists)
        except Refused as why:
            report.refuse(decision, str(why))
            report.refuse(place, "its decision is refused")
            return
    decisions.create(row, decided[1] if decided else None, lists.places)


def _created_row(place: PatchLine, lists: _Lists) -> PlaceRow:
    """The new row of a `create` line, or Refused."""
    if isinstance(place, RefusedLine):
        raise Refused(place.problem)
    return newplaces.new_row(place.entry, lists.places)


def _decided(
    line: PatchLine, row_of: Callable[[str], PlaceRow], lists: _Lists
) -> tuple[PlaceRow, Decision] | None:
    """What a decision line makes of its row (`row_of` finds it by the
    entry's id): the row and the decision, None for one withdrawn in the
    browser -- or Refused."""
    if isinstance(line, RefusedLine):
        raise Refused(line.problem)
    action = ACTIONS[line.entry["action"]]
    if action is None:
        return None  # withdrawn in the browser
    row = row_of(line.entry["id"])
    return row, action(line.entry, row, lists.standing_for(row))


def _write(lists: _Lists, decisions: _Decisions) -> None:
    """Write what the decisions changed: curation.csv first, places.csv
    last.  When the places.csv write fails (a spreadsheet saved it meanwhile,
    say), the curation rows come out again, so a `local/<slug>` row never
    lands without its position and a failed apply leaves both files as they
    were -- what became of curation.csv then goes into the log."""
    if not (decisions.report.applied or decisions.report.created):
        return
    written = _append_curation(lists.curation, decisions.new_curation)
    try:
        lists.places.write()
    except BaseException:
        if written:
            added = [c["osm"] for c in decisions.new_curation]
            decisions.report.log.append(unwrite_curation(lists.curation, written, added))
        raise


def _append_curation(curation: Appendable, new_rows: Sequence[Mapping[str, str]]) -> str | None:
    """Append the rows to curation.csv, if it still is what apply checked;
    -> the digest of the file as written, None when there was nothing to
    append."""
    if not new_rows:
        return None
    text = curation.with_rows(new_rows)
    files.atomic_write(curation.path, text, expect=curation.digest)
    return files.digest(text)


def _keep_refused(snapshot: str, live: str, kept_back: Sequence[PatchLine]) -> list[str]:
    """Append what apply refused back to the live patch; -> where the
    applied patch went and what was kept, for the log."""
    said = [f"patch applied, moved to {snapshot}"]
    if kept_back:
        # a refused decision is not lost: it goes back into the patch (and
        # so stays "done" in the browser) until fixed or cleared
        n = patch.append_back(live, kept_back)
        said.append(
            f"{n} refused entr{'y' if n == 1 else 'ies'} kept in {live}"
            + (
                f" ({len(kept_back) - n} decided again in the browser meanwhile)"
                if n < len(kept_back)
                else ""
            )
        )
    return said


def unwrite_curation(curation: Appendable, written: str, added: Sequence[str]) -> str:
    """Undo apply's curation.csv write after the places.csv write failed: put
    back the file as it was read (no file, if there was none), unless someone
    changed it after apply wrote it (`written`, its digest) -- then say
    which rows to take out by hand.  -> what became of the file."""
    path = curation.path
    try:
        if curation.data is not None:
            files.atomic_write(path, curation.data, expect=written)
        elif files.fingerprint(path) == written:
            os.unlink(path)
        else:
            raise errors.Conflict(f"{path} changed on disk meanwhile")
    except (OSError, errors.PipelineError) as exc:
        return (
            f"error: could not take the new rows out of {path} again ({exc}) "
            f"-- delete the rows for {', '.join(added)} by hand before the next "
            f"apply"
        )
    return f"{path} put back as it was"


# ------------------------------------------------------------------- main ---
@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    argparser, apply_only = parser()
    args = argparser.parse_args(
        with_subcommand(sys.argv[1:] if argv is None else argv, argparser, apply_only)
    )
    ws = cli.workspace(args)
    reg = dialects.read(ws.dialects)
    if args.cmd == "apply":
        report = apply(ws, reg, dry_run=args.dry_run, keep=args.keep)
        cli.say(report.log, report.warnings)
        return 1 if report.refused else 0
    cli.say(worklist.export(ws, reg).log)
    return 0


def with_subcommand(
    argv: Sequence[str], argparser: argparse.ArgumentParser, apply_only: Collection[str]
) -> list[str]:
    """`argv`, with `export` in front when it names no subcommand: export is
    what one runs every time.  An option only `apply` takes stops it then
    (`frasch curate --dry-run` meant `apply --dry-run`)."""
    if argv and argv[0] in ("export", "apply", "-h", "--help"):
        return list(argv)
    if option := next((a for a in argv if a.split("=")[0] in apply_only), None):
        argparser.error(
            f"{option} belongs to `apply`: did you mean `frasch curate apply {' '.join(argv)}`?"
        )
    return ["export", *argv]


def options_of(argparser: argparse.ArgumentParser) -> set[str]:
    return {o for action in argparser._actions for o in action.option_strings}


def parser() -> tuple[argparse.ArgumentParser, set[str]]:
    """-> (the parser, the options only its `apply` subcommand takes)."""
    ap = cli.parser("curate", __doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="write the worklist for the browser", allow_abbrev=False)
    cli.add_workspace_options(ex, "names", "dialects", "matches", "worklist", "work")

    ap_ = sub.add_parser("apply", help="write the browser's decisions back", allow_abbrev=False)
    cli.add_workspace_options(ap_, "names", "dialects", "curation", "patch", "work")
    ap_.add_argument(
        "--dry-run", action="store_true", help="print what would change and write nothing"
    )
    ap_.add_argument(
        "--keep", action="store_true", help="do not rename the patch file after applying it"
    )
    return ap, options_of(ap_) - options_of(ex)
