"""match.py and the extracts behind candidates.jsonl (#24): its readers skip
the header, and a run warns when the set of extracts changed since the last
one -- dropping the Denmark extract clears every `auto` row only it has."""
from __future__ import annotations

import json

from frasch import curate
from frasch import match
from frasch import placelist
from frasch.nameindex import NameIndex
from frasch.candidates import read_records
from conftest import cand, places_text, write_candidates

SH = {"file": "schleswig-holstein-latest.osm.pbf",
      "replication_timestamp": "2026-09-20T20:21:02Z"}
DK = {"file": "denmark-latest.osm.pbf",
      "replication_timestamp": "2026-09-21T20:20:00Z"}
HEADER = {"header": {"extracts": [SH]}}
TOFTUM = cand("n", 240044107, 8.83, 54.71, place="village", name="Toftum")
HOYER = cand("n", 26854466, 8.693, 54.9602, src="denmark", place="town",
             name="Højer", name__de="Hoyer", name__da="Højer")
ROWS = [{"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"},
        {"id": "huuger", "kind": "settlement", "mooring": "Huuger", "de": "Hoyer"}]


def test_the_index_skips_the_header(tmp_path):
    index = NameIndex(read_records(str(write_candidates(tmp_path / "c.jsonl", HEADER, TOFTUM))))
    assert [r["id"] for r in index.recs] == [240044107]


def test_the_curation_export_skips_the_header(tmp_path):
    path = write_candidates(tmp_path / "c.jsonl", HEADER, TOFTUM)
    kept = curate.stream_records(str(path), {("n", 240044107)}, set())
    assert [r["id"] for r in kept] == [240044107]


# ------------------------------------------------------------ extract set ---
def run_match(world, extracts, *extra):
    """match.py on ROWS against candidates built from `extracts` (None: a file
    from before the header); the extracts of HOYER's are DK's only."""
    recs = [TOFTUM] + ([HOYER] if extracts and DK["file"] in
                       {e["file"] for e in extracts} else [])
    header = [{"header": {"extracts": extracts}}] if extracts is not None else []
    cands = write_candidates(world / "work" / "candidates.jsonl", *header, *recs)
    places = world / "places.csv"
    if not places.exists():
        places.write_text(places_text(ROWS), encoding="utf-8")
    assert match.main(["--names", str(places), "--candidates", str(cands),
                       "--matches", str(world / "work" / "matches.csv"),
                       "--report", str(world / "REPORT.md"), "--offline",
                       "--wikidata-cache", str(world / "work" / "wd.json"),
                       *extra]) == 0


def recorded(world):
    path = world / "work" / "match-extracts.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def statuses(world):
    rows, _ = placelist.read(str(world / "places.csv"))
    return {r["id"]: r["status"] for r in rows}


def test_a_run_records_the_extracts_it_used(world):
    run_match(world, [SH, DK])
    assert recorded(world) == {"extracts": [SH, DK]}


def test_a_dry_run_records_nothing(world):
    run_match(world, [SH, DK], "--dry-run")
    assert recorded(world) is None


def test_a_dropped_extract_is_named_and_its_rows_said_to_be_cleared(world, capsys):
    run_match(world, [SH, DK])
    assert statuses(world) == {"toftem": "auto", "huuger": "auto"}
    capsys.readouterr()
    run_match(world, [SH])
    err = capsys.readouterr().err
    assert "dropped: denmark-latest.osm.pbf" in err
    assert "cleared" in err
    assert statuses(world) == {"toftem": "auto", "huuger": ""}
    assert recorded(world) == {"extracts": [SH]}


def test_an_added_extract_is_named(world, capsys):
    run_match(world, [SH])
    capsys.readouterr()
    run_match(world, [SH, DK], "--dry-run")
    assert "added: denmark-latest.osm.pbf" in capsys.readouterr().err


def test_a_refreshed_extract_is_no_warning(world, capsys):
    run_match(world, [SH, DK])
    capsys.readouterr()
    run_match(world, [dict(SH, replication_timestamp="2026-09-27T20:21:02Z"), DK])
    assert capsys.readouterr().err == ""


def test_candidates_without_a_header_are_to_be_rebuilt(world, capsys):
    run_match(world, None)
    assert "build_candidates.py" in capsys.readouterr().err
    assert recorded(world) is None
