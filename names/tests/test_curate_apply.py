"""`curate.py apply` loses no decision and writes nothing half (#21, M1),
and finds each decision's row by its id however the list changed (#23)."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest

from frasch import curate
from frasch import match
from frasch import placelist
from frasch.paths import StrPath
from conftest import CURATION_HEADER, places_text, write_candidates

ROWS = [
    {"id": "taarep", "kind": "settlement", "mooring": "Taarep", "de": "Dorf"},  # line 2
    {"id": "uurd", "kind": "settlement", "mooring": "Uurd", "de": "Ort"},  # line 3
    {
        "id": "hus",
        "kind": "settlement",
        "mooring": "Hüs",
        "de": "Haus",  # line 4
        "osm": "node/9",
        "status": "ok",
    },
]


def entry(line: int, **kw: object) -> dict[str, object]:
    row = ROWS[line - 2]
    return {
        "id": row["id"],
        "line": line,
        "kind": row["kind"],
        "name": row["mooring"],
        "de": row["de"],
        **kw,
    }


def append(path: Path, *entries: object) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def lines(path: Path) -> list[Any]:
    if not path.exists():
        return []
    # split at newlines only, as a file is read: `splitlines` also splits
    # inside a JSON string that holds a line separator (U+2028)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


@dataclasses.dataclass
class World:
    work: Path
    places: Path
    curation: Path
    patch: Path

    def apply(self, *extra: str) -> int:
        return curate.main(
            [
                "apply",
                "--names",
                str(self.places),
                "--curation",
                str(self.curation),
                "--patch",
                str(self.patch),
                *extra,
            ]
        )


@pytest.fixture
def w(world: Path) -> World:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    return World(
        work=world / "work",
        places=world / "places.csv",
        curation=world / "curation.csv",
        patch=world / "work" / "curate-patch.jsonl",
    )


def during_read(monkeypatch: pytest.MonkeyPatch, action: Callable[[], object]) -> None:
    """Run `action` just before apply reads its snapshot of the patch -- the
    moment the dev server's next append can arrive."""
    real = curate.read_patch

    def hooked(path: StrPath) -> list[curate.PatchLine]:
        action()
        return real(path)

    monkeypatch.setattr(curate, "read_patch", hooked)


def archived(w: World) -> list[Path]:
    return sorted(p for p in w.work.iterdir() if ".applied." in p.name)


def test_applies_and_archives(w: World) -> None:
    append(w.patch, entry(2, action="osm", osm="node/1"))
    assert w.apply() == 0
    assert "node/1" in w.places.read_text(encoding="utf-8")
    assert not w.patch.exists()
    assert len(archived(w)) == 1


def test_entry_appended_during_apply_stays_pending(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    append(w.patch, entry(2, action="osm", osm="node/1"))
    late = entry(3, action="skip")
    during_read(monkeypatch, lambda: append(w.patch, late))
    assert w.apply() == 0
    assert lines(w.patch) == [late]  # not archived, not truncated
    assert "skip" not in w.places.read_text(encoding="utf-8")
    assert [e["line"] for e in lines(archived(w)[0])] == [2]


def test_refused_entries_are_appended_back(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    refused = entry(4, action="osm", osm="node/5")  # row 4 is decided by hand
    append(w.patch, entry(2, action="osm", osm="node/1"), refused)
    late = entry(3, action="skip")
    during_read(monkeypatch, lambda: append(w.patch, late))
    assert w.apply() == 1
    assert lines(w.patch) == [late, refused]


def test_refused_entry_redecided_meanwhile_is_not_appended_back(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    refused = entry(4, action="osm", osm="node/5")
    append(w.patch, refused)
    newer = entry(4, action="clear")
    during_read(monkeypatch, lambda: append(w.patch, newer))
    assert w.apply() == 1
    assert lines(w.patch) == [newer]  # the newer decision wins


def test_a_newer_decision_is_found_whatever_characters_its_note_has(
    w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the browser's JSON.stringify writes a line separator (U+2028) as it is:
    # it ends no line of the patch, and hides no newer decision
    refused = entry(4, action="osm", osm="node/5")
    append(w.patch, refused)
    newer = entry(4, action="skip", note="erst\u2028dann")
    during_read(monkeypatch, lambda: append(w.patch, newer))
    assert w.apply() == 1
    assert lines(w.patch) == [newer]


def test_bad_curation_csv_leaves_places_csv_untouched(
    w: World, capsys: pytest.CaptureFixture[str]
) -> None:
    w.curation.write_text("osm,name,lat,lon,note\n", encoding="utf-8")  # columns missing
    append(
        w.patch,
        entry(2, action="local", slug="taarep", lat=54.6, lon=8.9),
        entry(3, action="osm", osm="node/1"),
    )
    before, patch_before = w.places.read_bytes(), w.patch.read_bytes()
    assert w.apply() == 1
    assert "missing column" in capsys.readouterr().err
    assert w.places.read_bytes() == before
    assert w.patch.read_bytes() == patch_before
    assert archived(w) == []


def test_places_csv_changed_meanwhile_writes_nothing_and_restores_the_patch(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9)
    append(w.patch, first)
    late = entry(3, action="skip")
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])

    def meanwhile() -> None:
        w.places.write_text(theirs, encoding="utf-8")  # a spreadsheet saves
        append(w.patch, late)  # the browser appends

    during_read(monkeypatch, meanwhile)
    assert w.apply() == 1
    assert "changed on disk" in capsys.readouterr().err
    assert w.places.read_text(encoding="utf-8") == theirs
    assert w.curation.read_text(encoding="utf-8") == CURATION_HEADER
    assert lines(w.patch) == [first, late]  # in decision order
    assert archived(w) == []


def test_curation_csv_changed_meanwhile_writes_nothing(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9)
    append(w.patch, first)
    theirs = CURATION_HEADER + "local/nai,Neu,54.7,8.8,,,,,by hand\n"
    before = w.places.read_bytes()
    during_read(monkeypatch, lambda: w.curation.write_text(theirs, encoding="utf-8"))
    assert w.apply() == 1
    assert "changed on disk" in capsys.readouterr().err
    assert w.places.read_bytes() == before
    assert w.curation.read_text(encoding="utf-8") == theirs
    assert lines(w.patch) == [first]
    assert archived(w) == []


def test_failed_places_write_removes_a_new_curation_csv(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """curation.csv is written first; a places.csv write that then fails
    takes it out again -- here, a file that did not exist before."""
    w.curation.unlink()
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9))
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])
    during_read(monkeypatch, lambda: w.places.write_text(theirs, encoding="utf-8"))
    assert w.apply() == 1
    assert "changed on disk" in capsys.readouterr().err
    assert not w.curation.exists()
    assert w.places.read_text(encoding="utf-8") == theirs


def test_curation_csv_edited_during_rollback_is_left_alone(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9))
    theirs = CURATION_HEADER + "local/nai,Neu,54.7,8.8,,,,,by hand\n"

    def failing_write(*a: object, **kw: object) -> NoReturn:
        w.curation.write_text(theirs, encoding="utf-8")  # a hand edit lands
        raise OSError("disk full")

    monkeypatch.setattr(placelist, "write", failing_write)
    with pytest.raises(OSError):
        w.apply()
    assert w.curation.read_text(encoding="utf-8") == theirs
    assert "delete the rows for local/taarep by hand" in capsys.readouterr().err


def test_local_decision_writes_both_files(w: World) -> None:
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9, note="by the dyke"))
    assert w.apply() == 0
    assert "local/taarep" in w.places.read_text(encoding="utf-8")
    assert w.curation.read_text(encoding="utf-8") == (
        CURATION_HEADER + "local/taarep,Dorf,54.6,8.9,,,,,by the dyke\n"
    )


def test_dry_run_and_keep_leave_the_patch_in_place(w: World) -> None:
    append(w.patch, entry(2, action="osm", osm="node/1"))
    before = w.places.read_bytes()
    w.apply("--dry-run")
    assert w.places.read_bytes() == before
    assert w.patch.exists() and archived(w) == []
    w.apply("--keep")
    assert "node/1" in w.places.read_text(encoding="utf-8")
    assert w.patch.exists() and archived(w) == []


# ------------------------------------------------------------ row ids (#23) ---
def rows_by_id(w: World) -> dict[str, placelist.PlaceRow]:
    return {r["id"]: r for r in placelist.read(str(w.places))[0]}


def test_a_withdrawn_decision_stays_withdrawn_whatever_line_it_was_sent_with(w: World) -> None:
    # M2: the browser sent `osm` from line 11 and `clear` from line 12 (a row
    # had been added above in between) -- one row, so the clear wins
    append(
        w.patch,
        entry(2, action="osm", osm="node/1") | {"line": 11},
        entry(2, action="clear") | {"line": 12},
    )
    assert w.apply() == 0
    assert (rows_by_id(w)["taarep"]["osm"], rows_by_id(w)["taarep"]["status"]) == ("", "")


def kirchwarft(ident: str, hint: str) -> dict[str, str]:
    return {
        "id": ident,
        "kind": "warft",
        "mooring": "Schörkewärw",
        "de": "Kirchwarft",
        "hint": hint,
    }


SESSION = [
    {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
    kirchwarft("schorkewarw", "Hooge"),
    kirchwarft("schorkewarw-2", "Ockholm"),
    kirchwarft("schorkewarw-3", "Langeneß"),
    kirchwarft("schorkewarw-4", "Oland"),
]


def test_a_curation_session_survives_hand_edits_to_the_list(w: World) -> None:
    # the worklist: every row is `not_found` (no candidates at all)
    w.places.write_text(places_text(SESSION), encoding="utf-8")
    cands = write_candidates(w.work / "candidates.jsonl")
    assert (
        match.main(
            [
                "--names",
                str(w.places),
                "--candidates",
                str(cands),
                "--matches",
                str(w.work / "matches.csv"),
                "--report",
                str(w.work / "REPORT.md"),
                "--offline",
                "--wikidata-cache",
                str(w.work / "wd.json"),
            ]
        )
        == 0
    )
    worklist = w.work / "curate.json"
    assert (
        curate.main(
            [
                "export",
                "--names",
                str(w.places),
                "--matches",
                str(w.work / "matches.csv"),
                "--candidates",
                str(cands),
                "--out",
                str(worklist),
            ]
        )
        == 0
    )
    # the browser decides every row of it, one object each
    exported = json.loads(worklist.read_text(encoding="utf-8"))["rows"]
    decided = {row["id"]: f"node/{n}" for n, row in enumerate(exported, start=1)}
    append(
        w.patch,
        *(
            {
                "id": row["id"],
                "line": row["line"],
                "kind": row["kind"],
                "name": row["name"],
                "de": row["de"],
                "action": "osm",
                "osm": decided[row["id"]],
            }
            for row in exported
        ),
    )
    # meanwhile, by hand: a row on top, and a German name corrected
    edited = [
        {"id": "naibel", "kind": "settlement", "mooring": "Naibel", "de": "Niebüll"},
        SESSION[0] | {"de": "Toftum (Nordfriesland)"},
        *SESSION[1:],
    ]
    w.places.write_text(places_text(edited), encoding="utf-8")

    assert w.apply() == 0
    rows = rows_by_id(w)
    assert sorted(decided) == sorted(r["id"] for r in SESSION)
    assert {i: rows[i]["osm"] for i in decided} == decided
    assert rows["naibel"]["osm"] == ""


def test_every_decision_without_an_id_is_refused_and_kept(w: World) -> None:
    # a patch written before the row ids: nothing to find the row by, and
    # none of the decisions may vanish into the archive
    old = [{k: v for k, v in entry(n, action="skip").items() if k != "id"} for n in (2, 3)]
    append(w.patch, *old)
    assert w.apply() == 1
    assert lines(w.patch) == old


def test_an_entry_that_breaks_the_patch_schema_is_refused_and_kept(
    w: World, capsys: pytest.CaptureFixture[str]
) -> None:
    # names/curate-patch.schema.json is the contract with the browser; a
    # hand-edited or foreign line must not crash apply or reach the list
    broken = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9, note=42)
    append(w.patch, broken)
    before = w.places.read_bytes()
    assert w.apply() == 1
    assert "42 is not of type 'string'" in capsys.readouterr().out
    assert w.places.read_bytes() == before
    assert lines(w.patch) == [broken]


def test_a_refused_line_with_keys_the_schema_does_not_know_comes_back_unchanged(
    w: World,
) -> None:
    # apply keeps what it knows about a line apart from the line's value: a
    # hand-edited line with keys of its own is kept as written
    foreign = entry(2, action="skip") | {"_raw": "x", "_patch_line": 7}
    append(w.patch, foreign)
    assert w.apply() == 1
    assert lines(w.patch) == [foreign]


@pytest.mark.parametrize(
    "broken",
    [
        {"id": "uurd", "action": "skip", "line": "3"},  # a line number as text
        {"id": ["uurd"], "action": "skip"},  # an id that is no string
        [1, 2],  # not an object at all
    ],
)
def test_a_line_that_is_no_patch_entry_is_refused_and_kept_not_a_crash(
    w: World, broken: object
) -> None:
    # it reaches apply before any row is looked at: the read of the patch
    # itself must not trip over it
    good = entry(2, action="skip")
    append(w.patch, good, broken)
    assert w.apply() == 1
    assert rows_by_id(w)["taarep"]["status"] == "skip"
    assert lines(w.patch) == [broken]


def test_a_broken_line_about_a_row_holds_back_its_earlier_decision(
    w: World, capsys: pytest.CaptureFixture[str]
) -> None:
    # the newest line about a row is what counts, broken or not: a broken
    # `clear` must not let the decision it meant to withdraw through
    decided = entry(2, action="skip")
    broken_clear = {"id": "taarep", "action": "clear", "line": "2"}
    append(w.patch, decided, broken_clear)
    assert w.apply() == 1
    assert "line: '2' is not of type 'integer'" in capsys.readouterr().out
    assert rows_by_id(w)["taarep"]["status"] == ""
    assert lines(w.patch) == [broken_clear]


def test_a_line_that_is_no_object_says_so(w: World, capsys: pytest.CaptureFixture[str]) -> None:
    append(w.patch, [1, 2])
    assert w.apply() == 1
    assert "not a JSON object" in capsys.readouterr().out


# ------------------------------------------------------- what apply prints ---
def mixed_patch(w: World) -> None:
    """Two decisions apply takes, two it refuses."""
    append(
        w.patch,
        entry(2, action="local", slug="taarep", lat=54.6, lon=8.9, polygon_km2=1.5),
        entry(3, action="osm", osm="node/1", wikidata="Q5"),
        entry(4, action="skip"),  # decided by hand
        {"id": "nai", "action": "skip"},  # no such row
    )


def test_apply_logs_each_decision_and_sums_up(w: World, capsys: pytest.CaptureFixture[str]) -> None:
    mixed_patch(w)
    assert w.apply() == 1
    (snapshot,) = archived(w)
    assert capsys.readouterr().out == (
        # an entry without a `line` comes first
        f"  refused patch line 4 (None / None): no row with id 'nai' in {w.places} "
        "(deleted since the export?)\n"
        f"  {w.places}:2 Taarep (Dorf): osm = local/taarep, status = ok; "
        f"{w.curation} += 54.6/8.9, polygon_km2 = 1.5\n"
        f"  {w.places}:3 Uurd (Ort): osm = node/1, wikidata = Q5, status = ok\n"
        f"  refused patch line 3 (Hüs / Haus): {w.places}:4 is not the matcher's "
        "to fill (status=ok, osm=node/9)\n"
        f"patch applied, moved to {snapshot}\n"
        f"2 refused entries kept in {w.patch}\n"
        f"2 row(s) written to {w.places}, 1 appended to {w.curation}, 2 refused\n"
    )
    assert w.curation.read_text(encoding="utf-8") == (
        CURATION_HEADER + "local/taarep,Dorf,54.6,8.9,place=island,,,1.5,\n"
    )


def test_dry_run_says_what_would_change(w: World, capsys: pytest.CaptureFixture[str]) -> None:
    mixed_patch(w)
    assert w.apply("--dry-run") == 1
    out = capsys.readouterr().out
    assert out.endswith(
        "dry run: 2 row(s) would change, 1 curation row(s) would be appended, "
        "2 refused -- nothing written\n"
    )
    assert out.count("\n") == 5  # the four decisions above, then the sum


def test_keep_applies_without_archiving_or_appending_back(
    w: World, capsys: pytest.CaptureFixture[str]
) -> None:
    mixed_patch(w)
    patch_before = w.patch.read_bytes()
    assert w.apply("--keep") == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        f"2 row(s) written to {w.places}, 1 appended to {w.curation}, 2 refused"
    )
    assert w.patch.read_bytes() == patch_before


def test_a_refused_entry_decided_again_meanwhile_is_counted_apart(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    append(w.patch, entry(4, action="osm", osm="node/5"), {"id": "nai", "action": "skip"})
    during_read(monkeypatch, lambda: append(w.patch, entry(4, action="clear")))
    assert w.apply() == 1
    assert (
        f"1 refused entry kept in {w.patch} (1 decided again in the browser meanwhile)\n"
        in capsys.readouterr().out
    )


def test_a_local_slug_of_another_row_is_taken(w: World, capsys: pytest.CaptureFixture[str]) -> None:
    koog = {"id": "koog", "kind": "koog", "mooring": "Kuuch", "osm": "local/taarep"}
    w.places.write_text(places_text(ROWS + [koog]), encoding="utf-8")
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9))
    assert w.apply() == 1
    assert "local/taarep is already taken" in capsys.readouterr().out
    assert w.curation.read_text(encoding="utf-8") == CURATION_HEADER


def test_no_patch_is_an_error(w: World, capsys: pytest.CaptureFixture[str]) -> None:
    before = w.places.read_bytes()
    assert w.apply() == 1
    assert capsys.readouterr().err == (
        f"{w.patch} not found -- decide some rows in the browser first (web/, `?curate`)\n"
    )
    assert w.places.read_bytes() == before


def test_a_failed_apply_says_the_patch_is_restored(
    w: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    append(w.patch, entry(2, action="skip"))
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])
    during_read(monkeypatch, lambda: w.places.write_text(theirs, encoding="utf-8"))
    assert w.apply() == 1
    err = capsys.readouterr().err
    assert err.startswith(f"nothing applied -- {w.patch} restored\n")
    assert "changed on disk" in err
