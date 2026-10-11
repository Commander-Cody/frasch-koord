"""matchfile.py: work/matches.jsonl, what a run of the matcher made of each
row it owns -- written by `frasch match`, read by `frasch curate export`."""

from __future__ import annotations

from pathlib import Path

from frasch import matchfile
from frasch.candidates import Candidate
from frasch.matchresult import MatchResult, Outcome, RankedCandidate
from frasch.nameindex import NameIndex
from conftest import cand

KAMPEN = cand("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)", place="village")
KAMPEN_MUNICIPALITY = cand(
    "r",
    1147133,
    8.356739,
    54.967875,
    name="Kampen (Sylt)",
    boundary="administrative",
    admin_level="8",
    wikidata="Q27332",
)


def ranked(rec: Candidate, rank: int = 0) -> RankedCandidate:
    return {**rec, "rank": rank}


def round_trip(tmp_path: Path, result: MatchResult, *recs: Candidate) -> matchfile.Entry:
    """`result`, the result of a row `kaamp` among the candidates `recs`,
    written to a matches file and read back."""
    path = tmp_path / "matches.jsonl"
    entry = matchfile.entry("kaamp", result, (8.3, 54.9, 25.0), NameIndex(recs))
    matchfile.write(str(path), [entry])
    (read,) = matchfile.read(path)
    return read


def test_a_result_is_read_back_as_the_run_made_it(tmp_path: Path) -> None:
    result = MatchResult(
        Outcome.MATCHED,
        why="auto: location hint",
        refs=(("n", 240063898),),
        wikidata="Q27332",
        match_name="Kampen (Sylt)",
        match_tags="place=village",
        lonlat=(8.344065, 54.95377),
        candidates=(ranked(KAMPEN), ranked(KAMPEN_MUNICIPALITY, rank=2)),
    )
    assert round_trip(tmp_path, result, KAMPEN, KAMPEN_MUNICIPALITY) == {
        "id": "kaamp",
        "result": "matched",
        "why": "auto: location hint",
        "osm": "node/240063898",
        "wikidata": "Q27332",
        "match_name": "Kampen (Sylt)",
        "match_tags": "place=village",
        "lon": 8.344065,
        "lat": 54.95377,
        "hint_point": [8.3, 54.9, 25.0],
        "candidates": [
            {
                "ref": "node/240063898",
                "name": "Kampen (Sylt)",
                "class": "village",
                # 28.2 km north and 35.6 km west of the North Frisia centre (8.9, 54.7)
                "km": 45,
                "lon": 8.344065,
                "lat": 54.95377,
                "tags": "place=village",
                "in_sh": True,
                "rank": 0,
            },
            {
                "ref": "relation/1147133",
                "name": "Kampen (Sylt)",
                "class": "administrative",
                "km": 46,
                "lon": 8.356739,
                "lat": 54.967875,
                "tags": "boundary=administrative;admin_level=8",
                "wikidata": "Q27332",
                "in_sh": True,
                "rank": 2,
            },
        ],
    }


def listed(tmp_path: Path, *recs: Candidate) -> list[matchfile.ListedCandidate]:
    """The candidates of an ambiguous row among `recs`, of which it lists
    the first, as its entry of a matches file has them."""
    result = MatchResult(Outcome.AMBIGUOUS, candidates=(ranked(recs[0]),))
    return round_trip(tmp_path, result, *recs)["candidates"]


def test_a_candidate_keeps_a_name_with_a_semicolon_and_a_colon(tmp_path: Path) -> None:
    odd = cand("w", 188800550, 8.9, 54.7, name="Warft: Kirchwarft; Schörkewärw", place="hamlet")
    (c,) = listed(tmp_path, odd)
    assert c["name"] == "Warft: Kirchwarft; Schörkewärw"


def test_a_candidate_without_a_position_has_no_distance(tmp_path: Path) -> None:
    nowhere = cand("r", 1420394, None, None, name="Holm", boundary="administrative")
    (c,) = listed(tmp_path, nowhere)
    assert c["km"] is None


def test_a_candidate_of_the_denmark_extract_alone_is_not_in_schleswig_holstein(
    tmp_path: Path,
) -> None:
    (c,) = listed(tmp_path, cand("n", 7, 8.9, 54.7, src="denmark", name="Kampen", place="hamlet"))
    assert c["in_sh"] is False


def test_a_candidate_of_both_extracts_is_in_schleswig_holstein(tmp_path: Path) -> None:
    # an object near the border is in both extracts, once for each
    border = cand("n", 7, 8.9, 54.9, name="Seth", place="hamlet")
    (c,) = listed(tmp_path, border, {**border, "src": "denmark"})
    assert c["in_sh"] is True


def test_a_row_without_a_hint_has_no_hint_point(tmp_path: Path) -> None:
    path = tmp_path / "matches.jsonl"
    entry = matchfile.entry("kaamp", MatchResult(Outcome.NOT_FOUND), None, NameIndex([]))
    matchfile.write(str(path), [entry])
    assert [m["hint_point"] for m in matchfile.read(path)] == [None]
