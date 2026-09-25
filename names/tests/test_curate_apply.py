"""`curate.py apply` loses no decision and writes nothing half (#21, M1)."""
from __future__ import annotations

import json
import types

import pytest

import curate
from conftest import CURATION_HEADER, places_text

ROWS = [
    {"kind": "settlement", "mooring": "Taarep", "de": "Dorf"},           # line 2
    {"kind": "settlement", "mooring": "Uurd", "de": "Ort"},              # line 3
    {"kind": "settlement", "mooring": "Hüs", "de": "Haus",               # line 4
     "osm": "node/9", "status": "ok"},
]


def entry(line, **kw):
    row = ROWS[line - 2]
    return {"line": line, "kind": row["kind"], "name": row["mooring"],
            "de": row["de"], **kw}


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


def test_bad_curation_csv_leaves_places_csv_untouched(w):
    w.curation.write_text("osm,name,lat,lon,note\n", encoding="utf-8")  # columns missing
    append(w.patch, entry(2, action="local", slug="taarep", lat=54.6, lon=8.9),
           entry(3, action="osm", osm="node/1"))
    before, patch_before = w.places.read_bytes(), w.patch.read_bytes()
    with pytest.raises(SystemExit, match="missing column"):
        w.apply()
    assert w.places.read_bytes() == before
    assert w.patch.read_bytes() == patch_before
    assert archived(w) == []


def test_places_csv_changed_meanwhile_writes_nothing_and_restores_the_patch(w, monkeypatch):
    first = entry(2, action="local", slug="taarep", lat=54.6, lon=8.9)
    append(w.patch, first)
    late = entry(3, action="skip")
    theirs = places_text(ROWS + [{"kind": "settlement", "mooring": "Nai", "de": "Neu"}])

    def meanwhile():
        w.places.write_text(theirs, encoding="utf-8")   # a spreadsheet saves
        append(w.patch, late)                           # the browser appends

    during_read(monkeypatch, meanwhile)
    with pytest.raises(SystemExit, match="changed on disk"):
        w.apply()
    assert w.places.read_text(encoding="utf-8") == theirs
    assert w.curation.read_text(encoding="utf-8") == CURATION_HEADER
    assert lines(w.patch) == [first, late]              # in decision order
    assert archived(w) == []


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
