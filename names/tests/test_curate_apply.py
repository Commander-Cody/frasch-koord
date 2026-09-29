"""`curate.py apply` loses no decision and writes nothing half (#21, M1),
and finds each decision's row by its id however the list changed (#23)."""
from __future__ import annotations

import json
import types

import pytest

from frasch import curate
from frasch import match
from frasch import placelist
from conftest import CURATION_HEADER, places_text, write_candidates

ROWS = [
    {"id": "taarep", "kind": "settlement", "mooring": "Taarep", "de": "Dorf"},  # line 2
    {"id": "uurd", "kind": "settlement", "mooring": "Uurd", "de": "Ort"},       # line 3
    {"id": "hus", "kind": "settlement", "mooring": "Hüs", "de": "Haus",         # line 4
     "osm": "node/9", "status": "ok"},
]


def entry(line, **kw):
    row = ROWS[line - 2]
    return {"id": row["id"], "line": line, "kind": row["kind"],
            "name": row["mooring"], "de": row["de"], **kw}


def append(path, *entries):
    with open(path, "a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def lines(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


@pytest.fixture
def w(world):
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    w = types.SimpleNamespace(work=world / "work", places=world / "places.csv",
                              curation=world / "curation.csv",
                              patch=world / "work" / "curate-patch.jsonl")
    w.apply = lambda *extra: curate.main(
        ["apply", "--names", str(w.places), "--curation", str(w.curation),
         "--patch", str(w.patch), *extra])
    return w


def during_read(monkeypatch, action):
    """Run `action` just before apply reads its snapshot of the patch -- the
    moment the dev server's next append can arrive."""
    real = curate.read_patch

    def hooked(path):
        action()
        return real(path)

    monkeypatch.setattr(curate, "read_patch", hooked)


def archived(w):
    return sorted(p for p in w.work.iterdir() if ".applied." in p.name)


def test_applies_and_archives(w):
    append(w.patch, entry(2, action="osm", osm="node/1"))
    assert w.apply() == 0
    assert "node/1" in w.places.read_text(encoding="utf-8")
    assert not w.patch.exists()
    assert len(archived(w)) == 1


def test_entry_appended_during_apply_stays_pending(w, monkeypatch):
    append(w.patch, entry(2, action="osm", osm="node/1"))
    late = entry(3, action="skip")
    during_read(monkeypatch, lambda: append(w.patch, late))
    assert w.apply() == 0
    assert lines(w.patch) == [late]          # not archived, not truncated
    assert "skip" not in w.places.read_text(encoding="utf-8")
    assert [e["line"] for e in lines(archived(w)[0])] == [2]


def test_refused_entries_are_appended_back(w, monkeypatch):
    refused = entry(4, action="osm", osm="node/5")      # row 4 is decided by hand
    append(w.patch, entry(2, action="osm", osm="node/1"), refused)
    late = entry(3, action="skip")
    during_read(monkeypatch, lambda: append(w.patch, late))
    assert w.apply() == 1
    assert lines(w.patch) == [late, refused]


def test_refused_entry_redecided_meanwhile_is_not_appended_back(w, monkeypatch):
    refused = entry(4, action="osm", osm="node/5")
    append(w.patch, refused)
    newer = entry(4, action="clear")
    during_read(monkeypatch, lambda: append(w.patch, newer))
    assert w.apply() == 1
    assert lines(w.patch) == [newer]         # the newer decision wins


def test_bad_curation_csv_leaves_places_csv_untouched(w, capsys):
    w.curation.write_text("osm,name,lat,lon,note\n", encoding="utf-8")  # columns missing
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9),
           entry(3, action="osm", osm="node/1"))
    before, patch_before = w.places.read_bytes(), w.patch.read_bytes()
    assert w.apply() == 1
    assert "missing column" in capsys.readouterr().err
    assert w.places.read_bytes() == before
    assert w.patch.read_bytes() == patch_before
    assert archived(w) == []


def test_places_csv_changed_meanwhile_writes_nothing_and_restores_the_patch(w, monkeypatch, capsys):
    first = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9)
    append(w.patch, first)
    late = entry(3, action="skip")
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])

    def meanwhile():
        w.places.write_text(theirs, encoding="utf-8")   # a spreadsheet saves
        append(w.patch, late)                           # the browser appends

    during_read(monkeypatch, meanwhile)
    assert w.apply() == 1
    assert "changed on disk" in capsys.readouterr().err
    assert w.places.read_text(encoding="utf-8") == theirs
    assert w.curation.read_text(encoding="utf-8") == CURATION_HEADER
    assert lines(w.patch) == [first, late]              # in decision order
    assert archived(w) == []


def test_curation_csv_changed_meanwhile_writes_nothing(w, monkeypatch, capsys):
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


def test_failed_places_write_removes_a_new_curation_csv(w, monkeypatch, capsys):
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


def test_curation_csv_edited_during_rollback_is_left_alone(w, monkeypatch, capsys):
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9))
    theirs = CURATION_HEADER + "local/nai,Neu,54.7,8.8,,,,,by hand\n"

    def failing_write(*a, **kw):
        w.curation.write_text(theirs, encoding="utf-8")   # a hand edit lands
        raise OSError("disk full")

    monkeypatch.setattr(curate.placelist, "write", failing_write)
    with pytest.raises(OSError):
        w.apply()
    assert w.curation.read_text(encoding="utf-8") == theirs
    assert "delete the rows for local/taarep by hand" in capsys.readouterr().err


def test_local_decision_writes_both_files(w):
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9,
                          note="by the dyke"))
    assert w.apply() == 0
    assert "local/taarep" in w.places.read_text(encoding="utf-8")
    assert w.curation.read_text(encoding="utf-8") == (
        CURATION_HEADER + "local/taarep,Dorf,54.6,8.9,,,,,by the dyke\n")


def test_dry_run_and_keep_leave_the_patch_in_place(w):
    append(w.patch, entry(2, action="osm", osm="node/1"))
    before = w.places.read_bytes()
    w.apply("--dry-run")
    assert w.places.read_bytes() == before
    assert w.patch.exists() and archived(w) == []
    w.apply("--keep")
    assert "node/1" in w.places.read_text(encoding="utf-8")
    assert w.patch.exists() and archived(w) == []


# ------------------------------------------------------------ row ids (#23) ---
def rows_by_id(w):
    return {r["id"]: r for r in placelist.read(str(w.places))[0]}


def test_a_withdrawn_decision_stays_withdrawn_whatever_line_it_was_sent_with(w):
    # M2: the browser sent `osm` from line 11 and `clear` from line 12 (a row
    # had been added above in between) -- one row, so the clear wins
    append(w.patch, entry(2, action="osm", osm="node/1") | {"line": 11},
           entry(2, action="clear") | {"line": 12})
    assert w.apply() == 0
    assert (rows_by_id(w)["taarep"]["osm"], rows_by_id(w)["taarep"]["status"]) == ("", "")


def kirchwarft(ident, hint):
    return {"id": ident, "kind": "warft", "mooring": "Schörkewärw",
            "de": "Kirchwarft", "hint": hint}


SESSION = [{"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
           kirchwarft("schorkewarw", "Hooge"), kirchwarft("schorkewarw-2", "Ockholm"),
           kirchwarft("schorkewarw-3", "Langeneß"), kirchwarft("schorkewarw-4", "Oland")]


def test_a_curation_session_survives_hand_edits_to_the_list(w):
    # the worklist: every row is `not_found` (no candidates at all)
    w.places.write_text(places_text(SESSION), encoding="utf-8")
    cands = write_candidates(w.work / "candidates.jsonl")
    assert match.main(["--names", str(w.places), "--candidates", str(cands),
                       "--matches", str(w.work / "matches.csv"),
                       "--report", str(w.work / "REPORT.md"), "--offline",
                       "--wikidata-cache", str(w.work / "wd.json")]) == 0
    worklist = w.work / "curate.json"
    assert curate.main(["export", "--names", str(w.places),
                        "--matches", str(w.work / "matches.csv"),
                        "--candidates", str(cands), "--out", str(worklist)]) == 0
    # the browser decides every row of it, one object each
    exported = json.loads(worklist.read_text(encoding="utf-8"))["rows"]
    decided = {row["id"]: f"node/{n}" for n, row in enumerate(exported, start=1)}
    append(w.patch, *({"id": row["id"], "line": row["line"], "kind": row["kind"],
                       "name": row["name"], "de": row["de"], "action": "osm",
                       "osm": decided[row["id"]]} for row in exported))
    # meanwhile, by hand: a row on top, and a German name corrected
    edited = [{"id": "naibel", "kind": "settlement", "mooring": "Naibel", "de": "Niebüll"},
              SESSION[0] | {"de": "Toftum (Nordfriesland)"}, *SESSION[1:]]
    w.places.write_text(places_text(edited), encoding="utf-8")

    assert w.apply() == 0
    rows = rows_by_id(w)
    assert sorted(decided) == sorted(r["id"] for r in SESSION)
    assert {i: rows[i]["osm"] for i in decided} == decided
    assert rows["naibel"]["osm"] == ""


def test_every_decision_without_an_id_is_refused_and_kept(w):
    # a patch written before the row ids: nothing to find the row by, and
    # none of the decisions may vanish into the archive
    old = [{k: v for k, v in entry(n, action="skip").items() if k != "id"} for n in (2, 3)]
    append(w.patch, *old)
    assert w.apply() == 1
    assert lines(w.patch) == old


def test_an_entry_that_breaks_the_patch_schema_is_refused_and_kept(w, capsys):
    # names/curate-patch.schema.json is the contract with the browser; a
    # hand-edited or foreign line must not crash apply or reach the list
    broken = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9, note=42)
    append(w.patch, broken)
    before = w.places.read_bytes()
    assert w.apply() == 1
    assert "42 is not of type 'string'" in capsys.readouterr().out
    assert w.places.read_bytes() == before
    assert lines(w.patch) == [broken]


@pytest.mark.parametrize("broken", [
    {"id": "uurd", "action": "skip", "line": "3"},     # a line number as text
    {"id": ["uurd"], "action": "skip"},                # an id that is no string
    [1, 2],                                            # not an object at all
])
def test_a_line_that_is_no_patch_entry_is_refused_and_kept_not_a_crash(w, broken):
    # it reaches apply before any row is looked at: the read of the patch
    # itself must not trip over it
    good = entry(2, action="skip")
    append(w.patch, good, broken)
    assert w.apply() == 1
    assert rows_by_id(w)["taarep"]["status"] == "skip"
    assert lines(w.patch) == [broken]


def test_a_broken_line_about_a_row_holds_back_its_earlier_decision(w, capsys):
    # the newest line about a row is what counts, broken or not: a broken
    # `clear` must not let the decision it meant to withdraw through
    decided = entry(2, action="skip")
    broken_clear = {"id": "taarep", "action": "clear", "line": "2"}
    append(w.patch, decided, broken_clear)
    assert w.apply() == 1
    assert "line: '2' is not of type 'integer'" in capsys.readouterr().out
    assert rows_by_id(w)["taarep"]["status"] == ""
    assert lines(w.patch) == [broken_clear]


def test_a_line_that_is_no_object_says_so(w, capsys):
    append(w.patch, [1, 2])
    assert w.apply() == 1
    assert "not a JSON object" in capsys.readouterr().out
