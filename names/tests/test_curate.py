"""curate.py helpers: reading back match.py's `candidates` cell and reading
the decision patch.  (`apply`
itself is covered in test_curate_apply.py.)"""
from __future__ import annotations

import json


from frasch import curate
from frasch import match


def rec(t, id, lon, lat, **tags):
    return {"src": "schleswig-holstein", "t": t, "id": id, "lon": lon, "lat": lat,
            "cls": [], "tags": tags}


KAMPEN_SYLT = rec("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)", place="village")


# ------------------------------------------------------- parse_candidates ---
def test_candidate_round_trips_through_fmt_cand():
    (c,) = curate.parse_candidates(match.fmt_cand(KAMPEN_SYLT))
    assert c["key"] == ("n", 240063898)
    assert c["ref"] == "node/240063898"
    assert c["name"] == "Kampen (Sylt)"
    assert c["class"] == "village"
    # 28.2 km north and 35.6 km west of the North Frisia centre (8.9, 54.7)
    assert c["km"] == 45


def test_candidate_class_falls_back_past_place():
    peninsula = rec("n", 6337086093, 8.865555, 54.487371, name="Nordstrand",
                    natural="peninsula")
    (c,) = curate.parse_candidates(match.fmt_cand(peninsula))
    assert (c["ref"], c["class"]) == ("node/6337086093", "peninsula")


def test_candidate_name_with_a_colon_survives():
    odd = rec("w", 188800550, 8.9, 54.7, name="Warft: Kirchwarft", landuse="residential")
    (c,) = curate.parse_candidates(match.fmt_cand(odd))
    assert c["name"] == "Warft: Kirchwarft"
    assert c["class"] == "residential"
    assert c["km"] == 0


def test_candidate_without_position_has_no_distance():
    nowhere = rec("r", 1420394, None, None, name="Holm", boundary="administrative")
    (c,) = curate.parse_candidates(match.fmt_cand(nowhere))
    assert c["ref"] == "relation/1420394"
    assert c["km"] is None


def test_several_candidates_keep_their_order():
    hooge = rec("n", 11711096159, 8.544362, 54.572982, name="Kirchwarft", place="hamlet")
    ockholm = rec("n", 1333738478, 8.826992, 54.664965, name="Kirchwarft", place="hamlet")
    cell = ";".join([match.fmt_cand(hooge), match.fmt_cand(ockholm)])
    assert [c["ref"] for c in curate.parse_candidates(cell)] == [
        "node/11711096159", "node/1333738478"]


def test_unreadable_candidate_is_skipped():
    cell = "x/1:Holm:village:3;" + match.fmt_cand(KAMPEN_SYLT)
    assert [c["ref"] for c in curate.parse_candidates(cell)] == ["node/240063898"]


def test_empty_candidates_cell_is_no_candidate():
    assert curate.parse_candidates("") == []
    assert curate.parse_candidates(None) == []


# -------------------------------------------------------------- read_patch ---
def write_patch(path, *lines):
    path.write_text("".join(
        (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)) + "\n"
        for x in lines), encoding="utf-8")


IDS = {"Mursem": "mursem", "Hoonebel": "hoonebel"}


def entry(line, name, de, **kw):
    return {"id": IDS[name], "line": line, "kind": "settlement", "name": name,
            "de": de, **kw}


def test_last_decision_per_row_wins(tmp_path):
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="skip"),
                entry(2, "Mursem", "Morsum", action="osm", osm="node/1"))
    (e,) = curate.read_patch(p)
    assert (e["action"], e["osm"]) == ("osm", "node/1")


def test_patch_entries_come_back_in_line_order(tmp_path):
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(7, "Hoonebel", "Hunnebüll", action="skip"),
                entry(2, "Mursem", "Morsum", action="skip"))
    assert [e["line"] for e in curate.read_patch(p)] == [2, 7]


def test_same_line_but_another_row_is_a_separate_decision(tmp_path):
    # the line does not identify a row: it moves when rows are added
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="skip"),
                entry(2, "Hoonebel", "Hunnebüll", action="skip"))
    assert len(curate.read_patch(p)) == 2


def test_same_row_at_another_line_is_the_same_decision(tmp_path):
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="osm", osm="node/1"),
                entry(3, "Mursem", "Morsum", action="clear"))
    (e,) = curate.read_patch(p)
    assert e["action"] == "clear"


def test_broken_and_blank_lines_are_ignored(tmp_path, capsys):
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="skip"), "",
                '{"line": 3, "kind": "sett',
                entry(4, "Hoonebel", "Hunnebüll", action="skip"))
    assert [e["line"] for e in curate.read_patch(p)] == [2, 4]
    assert ":3: not JSON" in capsys.readouterr().err


def test_each_entry_knows_its_line_in_the_patch(tmp_path):
    p = tmp_path / "curate-patch.jsonl"
    write_patch(p, entry(2, "Mursem", "Morsum", action="skip"), "",
                entry(4, "Hoonebel", "Hunnebüll", action="skip"))
    assert [e["_patch_line"] for e in curate.read_patch(p)] == [1, 3]
